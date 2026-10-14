"""Test skill_optimization converters

质量评分在 JSON 列与 SkillQualityScore 之间的转换：缺失或非数值的维度按 0.0 处理。
"""

import pytest
from myrm_agent_harness.agent.skills.optimization.types import SkillQualityScore

from app.adapters.skill_optimization.converters import quality_score_to_dict, to_quality_score

_ZERO = SkillQualityScore(0.0, 0.0, 0.0, 0.0, 0.0)


@pytest.mark.parametrize("raw", [None, "0.5", [0.5], b"0.5"])
def test_unreadable_score_becomes_all_zero(raw):
    assert to_quality_score(raw) == _ZERO


def test_scalar_score_fills_every_dimension():
    assert to_quality_score(0.5) == SkillQualityScore(0.5, 0.5, 0.5, 0.5, 0.5)


def test_dict_score_keeps_numeric_dimensions_and_zeroes_the_rest():
    raw = {"success_rate": 0.9, "execution_time": 3, "token_efficiency": True, "user_satisfaction": "high"}

    assert to_quality_score(raw) == SkillQualityScore(0.9, 0.0, 3.0, 0.0, 0.0)


def test_dict_round_trip_preserves_every_dimension():
    score = SkillQualityScore(0.5, 0.25, 0.75, 0.5, 0.125)

    serialized = quality_score_to_dict(score)

    assert serialized["overall_score"] == pytest.approx(score.overall_score)
    assert to_quality_score(serialized) == score
