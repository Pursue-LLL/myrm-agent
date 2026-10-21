"""Tests for token_cost field in Skill model and store reader sorting."""

from __future__ import annotations

from datetime import datetime

from app.core.skills.models import Skill, SkillType
from app.core.skills.store.reader import sort_skills


class TestSkillTokenCostSerialization:
    """Skill.to_dict / from_dict round-trip for token_cost."""

    def _make_skill(self, *, token_cost: int | None = None) -> Skill:
        return Skill(
            id="test-skill",
            type=SkillType.PREBUILT,
            name="test",
            description="desc",
            storage_path="/tmp/test",
            token_cost=token_cost,
        )

    def test_to_dict_includes_token_cost(self) -> None:
        skill = self._make_skill(token_cost=1500)
        d = skill.to_dict()
        assert d["token_cost"] == 1500

    def test_to_dict_token_cost_none(self) -> None:
        skill = self._make_skill(token_cost=None)
        d = skill.to_dict()
        assert d["token_cost"] is None

    def test_from_dict_round_trip(self) -> None:
        skill = self._make_skill(token_cost=800)
        d = skill.to_dict()
        restored = Skill.from_dict(d)
        assert restored.token_cost == 800

    def test_from_dict_missing_token_cost(self) -> None:
        d = {
            "id": "t",
            "type": "prebuilt",
            "name": "t",
            "description": "d",
            "storage_path": "/tmp/t",
        }
        skill = Skill.from_dict(d)
        assert skill.token_cost is None

    def test_from_dict_token_cost_as_string(self) -> None:
        d = {
            "id": "t",
            "type": "prebuilt",
            "name": "t",
            "description": "d",
            "storage_path": "/tmp/t",
            "token_cost": "1200",
        }
        skill = Skill.from_dict(d)
        assert skill.token_cost == 1200


class TestSortSkillsByTokenCost:
    """sort_skills() with sort_by='token_cost'."""

    def _make_skill(self, name: str, token_cost: int | None) -> Skill:
        now = datetime.utcnow()
        return Skill(
            id=name,
            type=SkillType.PREBUILT,
            name=name,
            description="desc",
            storage_path=f"/tmp/{name}",
            token_cost=token_cost,
            created_at=now,
            updated_at=now,
        )

    def test_sort_asc(self) -> None:
        skills = [
            self._make_skill("big", 2000),
            self._make_skill("small", 100),
            self._make_skill("mid", 800),
        ]
        result = sort_skills(skills, sort_by="token_cost", order="asc")
        costs = [s.token_cost for s in result]
        assert costs == [100, 800, 2000]

    def test_sort_desc(self) -> None:
        skills = [
            self._make_skill("small", 100),
            self._make_skill("big", 2000),
        ]
        result = sort_skills(skills, sort_by="token_cost", order="desc")
        costs = [s.token_cost for s in result]
        assert costs == [2000, 100]

    def test_sort_none_token_cost_goes_last_in_desc(self) -> None:
        skills = [
            self._make_skill("none", None),
            self._make_skill("small", 100),
        ]
        result = sort_skills(skills, sort_by="token_cost", order="desc")
        assert result[0].name == "small"
        assert result[1].name == "none"

    def test_sort_none_token_cost_goes_first_in_asc(self) -> None:
        skills = [
            self._make_skill("big", 2000),
            self._make_skill("none", None),
        ]
        result = sort_skills(skills, sort_by="token_cost", order="asc")
        assert result[0].name == "none"
        assert result[1].name == "big"
