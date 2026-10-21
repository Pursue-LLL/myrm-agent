"""Contract tests: Skill A/B must use the same MatrixRunner API as memory_ab / matrix eval."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from myrm_agent_harness.eval.matrix import MatrixRunner


def test_matrix_runner_has_no_run_async() -> None:
    assert not hasattr(MatrixRunner, "run_async")


def test_matrix_runner_constructor_rejects_cases_kwarg() -> None:
    sig = inspect.signature(MatrixRunner.__init__)
    assert "cases" not in sig.parameters


def test_skill_ab_module_does_not_reference_dead_matrix_api() -> None:
    root = Path(__file__).resolve().parents[3]
    source = (root / "app/core/eval/skill_ab.py").read_text(encoding="utf-8")
    assert "run_async" not in source
    assert "cases=cases" not in source
    assert "run_multi_turn(cases)" in source


@pytest.mark.asyncio
async def test_run_skill_ab_background_aborts_cleanly_on_empty_benchmark(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.eval import skill_ab

    def _empty_cases(_benchmark_id: str, **kwargs: object) -> tuple[list[object], dict[str, str], bool]:
        return [], {}, False

    monkeypatch.setattr("app.core.eval.benchmarks.build_benchmark_cases", _empty_cases)

    await skill_ab.run_skill_ab_background(
        benchmark_id="operational-assurance",
        candidate_skill_id="skill-candidate",
        baseline_skill_id="skill-base",
    )

    status = skill_ab.get_skill_ab_status()
    assert status.get("is_running") is False
    assert "no eval cases" in str(status.get("error", "")).lower()
