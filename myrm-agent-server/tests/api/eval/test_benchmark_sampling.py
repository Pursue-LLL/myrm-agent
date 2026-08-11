"""Sampling (limit) tests for the benchmark case builder.

The limit feature caps the number of benchmark cases with a reproducible
random sample (fixed seed), letting users validate a small slice before
paying for a full run — aligned with simple-evals' ``num_examples``.
"""

from __future__ import annotations

from unittest.mock import patch

from myrm_agent_harness.eval import EvalCase, MultiTurnEvalCase, SemanticAssertion


def _fake_case(i: int) -> MultiTurnEvalCase:
    turn = EvalCase(
        message=f"task-{i}",
        semantic_assertions=[SemanticAssertion(type="llm_judge", expected="rubric")],
    )
    return MultiTurnEvalCase(turns=[turn])


def _cases(n: int) -> list[MultiTurnEvalCase]:
    return [_fake_case(i) for i in range(n)]


def test_build_benchmark_cases_limit_samples_browsecomp() -> None:
    """limit < full count returns exactly ``limit`` cases with a seed map."""
    full = _cases(100)
    full_seed_map = {f"task-{i}": f"seed-{i}" for i in range(100)}
    with (
        patch(
            "app.core.eval.browse_comp.build_browse_comp_cases",
            return_value=(full, full_seed_map),
        ),
    ):
        from app.core.eval.benchmarks import build_benchmark_cases

        cases, seed_map = build_benchmark_cases("browsecomp", limit=10)
        assert len(cases) == 10
        assert len(seed_map) == 10
        # Seed map keeps only the entries for the sampled cases.
        assert all(t.turns[0].message in seed_map for t in cases)


def test_build_benchmark_cases_limit_is_reproducible() -> None:
    """Two builds with the same limit pick the same tasks (fixed seed)."""
    full = _cases(50)
    with (
        patch(
            "app.core.eval.browse_comp.build_browse_comp_cases",
            return_value=(full, {}),
        ),
    ):
        from app.core.eval.benchmarks import build_benchmark_cases

        _, first = build_benchmark_cases("browsecomp", limit=8)
        _, second = build_benchmark_cases("browsecomp", limit=8)
    first_msgs = [t.turns[0].message for t in first]
    second_msgs = [t.turns[0].message for t in second]
    assert first_msgs == second_msgs


def test_build_benchmark_cases_limit_noop_when_above_count() -> None:
    """limit >= full count keeps every case (no sampling)."""
    full = _cases(5)
    with (
        patch(
            "app.core.eval.wb_bench.build_wb_bench_cases",
            return_value=(full, {}),
        ),
    ):
        from app.core.eval.benchmarks import build_benchmark_cases

        cases, _ = build_benchmark_cases("wb-bench-web", limit=99)
        assert len(cases) == 5


def test_build_benchmark_cases_no_limit_keeps_all() -> None:
    """No limit (or 0) keeps the full case set unchanged."""
    full = _cases(20)
    with (
        patch(
            "app.core.eval.browse_comp.build_browse_comp_cases",
            return_value=(full, {}),
        ),
    ):
        from app.core.eval.benchmarks import build_benchmark_cases

        cases, _ = build_benchmark_cases("browsecomp")
        assert len(cases) == 20
