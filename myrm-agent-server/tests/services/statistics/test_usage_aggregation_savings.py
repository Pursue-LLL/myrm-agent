"""Routing savings estimate: the counterfactual prices tokens, not calls."""

from __future__ import annotations

import pytest

from app.services.statistics.usage_aggregation import TierAccumulator, aggregate_usage, compute_estimated_savings


def _tier(calls: int, tokens_per_call: int, cost_per_mtok: float) -> TierAccumulator:
    acc = TierAccumulator()
    acc.calls = calls
    acc.total_tokens = calls * tokens_per_call
    acc.cost_usd = acc.total_tokens * cost_per_mtok / 1_000_000
    return acc


def test_savings_reprice_light_tokens_at_the_standard_per_token_cost() -> None:
    # 40 long standard turns ($3/Mtok) + 60 short light turns ($0.3/Mtok): the light turns are one tenth the size,
    # so running them on the standard model would have cost 180k tokens * $3/Mtok = $0.54, not 60 standard turns.
    tiers = {"standard": _tier(40, 30_000, 3.0), "simple": _tier(60, 3_000, 0.3)}

    savings = compute_estimated_savings(tiers)

    assert savings is not None
    assert savings["actualCost"] == pytest.approx(3.654)
    assert savings["hypotheticalCost"] == pytest.approx(4.14)
    assert savings["savings"] == pytest.approx(0.486)
    assert savings["savingsPercent"] == pytest.approx(11.7)


def test_savings_are_hidden_when_routing_costs_more_than_all_standard() -> None:
    tiers = {"standard": _tier(10, 10_000, 3.0), "reasoning": _tier(10, 10_000, 15.0)}

    assert compute_estimated_savings(tiers) is None


def test_savings_require_enough_standard_calls() -> None:
    tiers = {"standard": _tier(4, 10_000, 3.0), "simple": _tier(50, 1_000, 0.3)}

    assert compute_estimated_savings(tiers) is None


def test_savings_require_standard_token_data() -> None:
    tiers = {"standard": _tier(10, 0, 3.0), "simple": _tier(10, 1_000, 0.3)}

    assert compute_estimated_savings(tiers) is None


def test_aggregate_usage_reports_the_token_weighted_estimate() -> None:
    def row(tier: str, tokens: int, cost: float) -> tuple[dict[str, object], None]:
        return {"usage": {"total_tokens": tokens}, "costUsd": cost, "routingTier": tier}, None

    rows = [row("standard", 30_000, 0.09)] * 5 + [row("simple", 3_000, 0.0009)] * 5

    result = aggregate_usage(rows)

    savings = result["estimatedSavings"]
    assert isinstance(savings, dict)
    # all-standard cost: 165k tokens at $0.09 / 30k tokens = $0.495; actual: 0.45 + 0.0045
    assert savings["hypotheticalCost"] == pytest.approx(0.495)
    assert savings["savings"] == pytest.approx(0.0405)
