"""Tests for skill_to_response: the skill API payload shape and usage-stat coercion."""

from __future__ import annotations

import pytest

from app.api.skills.converter import skill_to_response
from app.api.skills.schemas import SkillResponse
from app.core.skills.models import Skill, SkillType


def _skill(usage_stats: dict[str, object] | None = None) -> Skill:
    return Skill(
        id="demo-skill",
        type=SkillType.PREBUILT,
        name="demo-skill",
        description="demo",
        storage_path="skills/prebuilt/demo-skill",
        usage_stats=usage_stats,
    )


def test_response_exposes_no_is_active_field() -> None:
    assert "is_active" not in SkillResponse.model_fields
    assert "is_active" not in skill_to_response(_skill()).model_dump()


def test_usage_stats_are_mapped_with_numeric_coercion() -> None:
    response = skill_to_response(
        _skill(
            {
                "call_count": "7",
                "success_count": 5,
                "failure_count": 2.0,
                "success_rate": "0.5",
                "lifecycle_status": "stale",
                "pinned": True,
            }
        )
    )
    stats = response.usage_stats
    assert (stats.call_count, stats.success_count, stats.failure_count) == (7, 5, 2)
    assert stats.success_rate == 0.5
    assert (stats.lifecycle_status, stats.pinned) == ("stale", True)


@pytest.mark.parametrize("malformed", [None, [], {}])
def test_malformed_numeric_usage_stats_fall_back_to_zero(malformed: object) -> None:
    stats = skill_to_response(_skill({"call_count": malformed, "success_rate": malformed})).usage_stats
    assert stats.call_count == 0
    assert stats.success_rate == 0.0
