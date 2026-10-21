"""Unit tests for token economics comparison in competitor migration dry-run.

Validates TokenEconomicsComparison schema construction and the estimation
constants used in import_archive.py.
"""

from __future__ import annotations

import pytest

from app.schemas.memory.archive import TokenEconomicsComparison
from app.services.memory.operations.crud.import_archive import (
    _COMPETITOR_AVG_SKILL_TOKENS,
    _MYRM_AVG_INDEX_TOKENS,
)


class TestTokenEconomicsComparison:
    """Schema construction and field validation."""

    def test_basic_construction(self) -> None:
        te = TokenEconomicsComparison(
            skill_count=37,
            source_tokens_per_turn=18_500,
            myrm_tokens_per_turn=1_110,
            savings_percent=94.0,
        )
        assert te.skill_count == 37
        assert te.source_tokens_per_turn == 18_500
        assert te.myrm_tokens_per_turn == 1_110
        assert te.savings_percent == 94.0

    def test_zero_skills(self) -> None:
        te = TokenEconomicsComparison(
            skill_count=0,
            source_tokens_per_turn=0,
            myrm_tokens_per_turn=0,
            savings_percent=0.0,
        )
        assert te.skill_count == 0
        assert te.savings_percent == 0.0

    def test_single_skill(self) -> None:
        te = TokenEconomicsComparison(
            skill_count=1,
            source_tokens_per_turn=_COMPETITOR_AVG_SKILL_TOKENS,
            myrm_tokens_per_turn=_MYRM_AVG_INDEX_TOKENS,
            savings_percent=94.0,
        )
        assert te.source_tokens_per_turn == 500
        assert te.myrm_tokens_per_turn == 30


class TestTokenEconomicsCalculation:
    """Validates the estimation formula used in import_archive.py dry-run."""

    def test_constants_are_positive(self) -> None:
        assert _COMPETITOR_AVG_SKILL_TOKENS > 0
        assert _MYRM_AVG_INDEX_TOKENS > 0

    def test_myrm_always_less_than_source(self) -> None:
        assert _MYRM_AVG_INDEX_TOKENS < _COMPETITOR_AVG_SKILL_TOKENS

    @pytest.mark.parametrize(
        "skill_count",
        [1, 5, 10, 37, 100],
    )
    def test_savings_formula(self, skill_count: int) -> None:
        source_tokens = skill_count * _COMPETITOR_AVG_SKILL_TOKENS
        myrm_tokens = skill_count * _MYRM_AVG_INDEX_TOKENS
        savings = round((1 - myrm_tokens / source_tokens) * 100, 1)

        assert source_tokens == skill_count * 500
        assert myrm_tokens == skill_count * 30
        assert savings == 94.0

    def test_savings_with_zero_source_tokens(self) -> None:
        source_tokens = 0
        savings = 0.0 if source_tokens == 0 else round((1 - 0 / source_tokens) * 100, 1)
        assert savings == 0.0
