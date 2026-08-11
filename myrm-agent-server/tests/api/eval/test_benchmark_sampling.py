"""Sampling (limit) tests for the benchmark case builder.

The limit feature caps the number of benchmark cases with a reproducible
random sample (fixed seed), letting users validate a small slice before
paying for a full run — aligned with simple-evals' ``num_examples``.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

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

        cases, seed_map, sampled = build_benchmark_cases("browsecomp", limit=10)
        assert len(cases) == 10
        assert len(seed_map) == 10
        assert sampled is True
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

        _, first, sampled = build_benchmark_cases("browsecomp", limit=8)
        _, second, _ = build_benchmark_cases("browsecomp", limit=8)
    first_msgs = [t.turns[0].message for t in first]
    second_msgs = [t.turns[0].message for t in second]
    assert first_msgs == second_msgs
    assert sampled is True


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

        cases, _, sampled = build_benchmark_cases("wb-bench-web", limit=99)
        assert len(cases) == 5
        assert sampled is False


def test_build_benchmark_cases_limit_equal_full_is_full_run() -> None:
    """A limit that equals the full count is a full run, not a sample.

    The builder reports ``sampled=False`` for it so callers never disclose a
    sample size for a run that used every task (e.g. entering 1266 for
    BrowseComp must not produce a "sampled" badge).
    """
    full = _cases(5)
    with (
        patch(
            "app.core.eval.wb_bench.build_wb_bench_cases",
            return_value=(full, {}),
        ),
    ):
        from app.core.eval.benchmarks import build_benchmark_cases

        cases, _, sampled = build_benchmark_cases("wb-bench-web", limit=5)
        assert len(cases) == 5
        assert sampled is False


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

        cases, _, sampled = build_benchmark_cases("browsecomp")
        assert len(cases) == 20
        assert sampled is False


def test_cold_registry_registers_browsecomp() -> None:
    """The registry is populated on import so run guards never see an
    unknown benchmark even on a cold process that only POSTs /run."""
    from app.core.eval.benchmarks import (
        benchmark_needs_judge,
        benchmark_required_tools,
        is_known_benchmark,
    )

    assert is_known_benchmark("browsecomp") is True
    assert benchmark_required_tools("browsecomp") == ("web_search",)
    assert benchmark_needs_judge("browsecomp") is True


@pytest.mark.asyncio
async def test_run_benchmark_background_sample_size_follows_sampled(monkeypatch) -> None:
    """run_benchmark_background discloses the limit only when sampling happened.

    The manifest sample size follows the builder's explicit ``sampled`` flag;
    a full run (limit at/above the case count) must never be flagged sampled.
    """
    from unittest.mock import AsyncMock

    import app.core.eval.service as service_mod

    service_mod._reset_benchmark_state()

    turn = EvalCase(
        message="task-1",
        semantic_assertions=[SemanticAssertion(type="llm_judge", expected="rubric")],
    )
    cases = [MultiTurnEvalCase(turns=[turn])]

    run_suite = AsyncMock()
    monkeypatch.setattr(service_mod, "run_eval_suite", run_suite)

    monkeypatch.setattr(
        "app.core.eval.benchmarks.build_benchmark_cases",
        lambda *args, **kwargs: (cases, {}, True),
    )
    await service_mod.run_benchmark_background("browsecomp", limit=50)
    assert run_suite.call_args.kwargs["limit"] == 50

    run_suite.reset_mock()
    monkeypatch.setattr(
        "app.core.eval.benchmarks.build_benchmark_cases",
        lambda *args, **kwargs: (cases, {}, False),
    )
    await service_mod.run_benchmark_background("browsecomp", limit=50)
    assert run_suite.call_args.kwargs["limit"] is None
    service_mod._reset_benchmark_state()


@pytest.mark.asyncio
async def test_build_eval_manifest_records_limit_and_judge(tmp_path, monkeypatch) -> None:
    """The eval manifest discloses the applied sample size and judge model."""
    from types import SimpleNamespace

    from app.core.eval.service import _build_eval_manifest

    async def fake_load() -> SimpleNamespace:
        return SimpleNamespace(
            model_cfg=SimpleNamespace(
                model="deepseek/deepseek-chat",
                api_key="sk-test",
                base_url="https://example.com",
            )
        )

    monkeypatch.setattr(
        "app.core.channel_bridge.config_loader.load_user_configs", fake_load
    )

    manifest = await _build_eval_manifest(
        None,
        "browsecomp",
        tmp_path / "no_cases.jsonl",
        benchmark_mode=True,
        judge_model="deepseek/deepseek-chat",
        limit=10,
    )
    assert manifest.limit == 10
    assert manifest.judge_model == "deepseek/deepseek-chat"
    assert manifest.benchmark_mode is True
