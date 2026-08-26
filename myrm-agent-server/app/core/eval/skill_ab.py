"""Skill A/B Evaluation — No-Skill vs Baseline-Skill vs Candidate-Skill three-arm comparative evaluation.

[INPUT]
- myrm_agent_harness.eval::MatrixRunner, AgentExecutor, SkillABReportData, SkillABArmMetrics
- app.core.eval.reports::DEFAULT_REPORTS_DIR
- app.core.eval.adaptive::AdaptiveEvalManager
- app.core.eval.model_config::_resolve_agent_model_label / _resolve_judge_config

[OUTPUT]
- get_skill_ab_status / abort_skill_ab: Progress query and abort control.
- run_skill_ab_background: Background three-arm evaluation run.
- get_latest_skill_ab_report / get_skill_ab_report / get_skill_ab_report_history.

[POS]
Reuses MatrixRunner with three executors differing strictly in their skill set:
1. no_skill: skill_ids_override = []
2. baseline: skill_ids_override = [baseline_skill_id] (or empty if none)
3. candidate: skill_ids_override = [candidate_skill_id]
All arms execute in isolated temporary sandboxes and aggregate 4D metrics.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness import __version__ as harness_version
from myrm_agent_harness.eval import (
    AgentExecutor,
    EvalManifest,
    SkillABArmMetrics,
    SkillABReportData,
)

from app.core.eval.executor import LocalEvalExecutor
from app.core.eval.reports import DEFAULT_REPORTS_DIR

if TYPE_CHECKING:
    from myrm_agent_harness.eval import MatrixRunner

logger = logging.getLogger(__name__)

_skill_ab_state: dict[str, object] = {
    "is_running": False,
    "stage": None,
    "current_arm": None,
    "profile_progress": 0,
    "profile_total": 0,
    "case_completed": 0,
    "case_total": 0,
    "error": None,
    "abort_requested": False,
}

_active_skill_ab_runner: "MatrixRunner | None" = None

DEFAULT_SKILL_AB_REPORTS_DIR = DEFAULT_REPORTS_DIR.parent / "skill_ab_reports"


def _init_skill_ab_state(benchmark_id: str) -> None:
    """Reset global state for a Skill A/B run."""
    _skill_ab_state.clear()
    _skill_ab_state.update(
        {
            "is_running": True,
            "stage": "downloading",
            "current_arm": None,
            "profile_progress": 0,
            "profile_total": 3,
            "case_completed": 0,
            "case_total": 0,
            "error": None,
            "abort_requested": False,
            "benchmark_id": benchmark_id,
        }
    )


def get_skill_ab_status() -> dict[str, object]:
    """Return the current Skill A/B evaluation state."""
    return dict(_skill_ab_state)


def abort_skill_ab() -> bool:
    """Request abort of the currently running Skill A/B evaluation."""
    global _active_skill_ab_runner
    if not _skill_ab_state.get("is_running"):
        return False
    _skill_ab_state["abort_requested"] = True
    if _active_skill_ab_runner is not None:
        _active_skill_ab_runner.abort()
    return True


async def run_skill_ab_background(
    benchmark_id: str,
    candidate_skill_id: str,
    baseline_skill_id: str | None = None,
    limit: int | None = None,
    reports_dir: Path | None = None,
) -> None:
    """Run a three-arm Skill A/B evaluation in the background."""
    global _active_skill_ab_runner

    if reports_dir is None:
        reports_dir = DEFAULT_SKILL_AB_REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)

    _init_skill_ab_state(benchmark_id)

    # 1. Resolve benchmark cases and configs
    from app.core.eval.benchmarks import build_benchmark_cases
    from app.core.eval.model_config import _resolve_agent_model_label, _resolve_judge_config

    try:
        cases, judge_config, max_tool_calls, max_iterations, blocked_hostnames, blocked_terms = await build_benchmark_cases(
            benchmark_id, progress_state=_skill_ab_state
        )
    except Exception as exc:
        _skill_ab_state["is_running"] = False
        _skill_ab_state["error"] = f"Failed to load benchmark: {exc}"
        return

    if not cases:
        _skill_ab_state["is_running"] = False
        _skill_ab_state["error"] = f"Benchmark '{benchmark_id}' contains no eval cases."
        return

    sampled = False
    if limit is not None and 0 < limit < len(cases):
        cases = cases[:limit]
        sampled = True

    _skill_ab_state["stage"] = "running"
    _skill_ab_state["case_total"] = len(cases)

    # 2. Build 3 Executors: no_skill, baseline, candidate
    executors: dict[str, AgentExecutor] = {
        "no_skill": LocalEvalExecutor(
            max_tool_calls=max_tool_calls,
            max_iterations=max_iterations,
            blocked_hostnames=blocked_hostnames,
            blocked_terms=blocked_terms,
            skill_ids_override=[],
        ),
        "baseline": LocalEvalExecutor(
            max_tool_calls=max_tool_calls,
            max_iterations=max_iterations,
            blocked_hostnames=blocked_hostnames,
            blocked_terms=blocked_terms,
            skill_ids_override=[baseline_skill_id] if baseline_skill_id else [],
        ),
        "candidate": LocalEvalExecutor(
            max_tool_calls=max_tool_calls,
            max_iterations=max_iterations,
            blocked_hostnames=blocked_hostnames,
            blocked_terms=blocked_terms,
            skill_ids_override=[candidate_skill_id],
        ),
    }

    from myrm_agent_harness.eval import MatrixRunner

    runner = MatrixRunner(
        cases=cases,
        executors=executors,
        judge_config=judge_config,
    )
    _active_skill_ab_runner = runner

    def _on_progress(arm: str, case_idx: int, total_cases: int) -> None:
        _skill_ab_state["current_arm"] = arm
        _skill_ab_state["case_completed"] = case_idx
        _skill_ab_state["case_total"] = total_cases
        arm_list = list(executors.keys())
        if arm in arm_list:
            _skill_ab_state["profile_progress"] = arm_list.index(arm)

    runner.set_progress_callback(_on_progress)

    try:
        matrix_result = await runner.run_async()

        # Compute per-arm metrics
        def _calc_metrics(arm_name: str, skill_id: str | None) -> SkillABArmMetrics:
            arm_res = matrix_result.per_profile_results.get(arm_name)
            if not arm_res:
                return SkillABArmMetrics(
                    arm_name=arm_name,
                    skill_id=skill_id,
                    pass_count=0,
                    total_cases=len(cases),
                    pass_rate=0.0,
                    avg_tool_calls=0.0,
                    total_tokens=0,
                    avg_latency_ms=0.0,
                )

            total_c = arm_res.total_cases or len(cases)
            pass_c = arm_res.pass_count
            pass_r = arm_res.pass_rate
            turn_results = getattr(arm_res, "turn_results", []) or []

            total_tool_calls = sum(len(t.response.tools_called) for t in turn_results)
            avg_tools = round(total_tool_calls / max(1, len(turn_results)), 2)

            total_tokens = sum(t.response.token_usage for t in turn_results)
            total_lat = sum(t.timings.total_ms for t in turn_results)
            avg_lat = round(total_lat / max(1, len(turn_results)), 2)

            return SkillABArmMetrics(
                arm_name=arm_name,
                skill_id=skill_id,
                pass_count=pass_c,
                total_cases=total_c,
                pass_rate=round(pass_r, 4),
                avg_tool_calls=avg_tools,
                total_tokens=total_tokens,
                avg_latency_ms=avg_lat,
            )

        no_skill_m = _calc_metrics("no_skill", None)
        base_m = _calc_metrics("baseline", baseline_skill_id)
        cand_m = _calc_metrics("candidate", candidate_skill_id)

        # Delta computations (Candidate vs Baseline)
        ref_arm = base_m if baseline_skill_id else no_skill_m
        succ_delta = cand_m.pass_rate - ref_arm.pass_rate

        token_savings = 0.0
        if ref_arm.total_tokens > 0:
            token_savings = (ref_arm.total_tokens - cand_m.total_tokens) / ref_arm.total_tokens

        step_red = 0.0
        if ref_arm.avg_tool_calls > 0:
            step_red = (ref_arm.avg_tool_calls - cand_m.avg_tool_calls) / ref_arm.avg_tool_calls

        verdict = "INCONCLUSIVE"
        if succ_delta > 0.05:
            verdict = "IMPROVED"
        elif succ_delta < -0.05:
            verdict = "REGRESSED"
        else:
            verdict = "EQUIVALENT"

        ts = int(time.time())
        report_data = SkillABReportData(
            dataset_id=benchmark_id,
            baseline_skill_id=baseline_skill_id,
            candidate_skill_id=candidate_skill_id,
            no_skill_metrics=no_skill_m,
            baseline_metrics=base_m,
            candidate_metrics=cand_m,
            success_rate_delta=succ_delta,
            token_savings_pct=token_savings,
            step_reduction_pct=step_red,
            verdict=verdict,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
            manifest=EvalManifest(
                harness_version=harness_version,
                matrix_fingerprint=f"skill-ab-{candidate_skill_id}-{ts}",
            ),
        )

        out_dict = report_data.to_dict()
        out_dict["agent_model"] = await _resolve_agent_model_label()
        out_dict["judge_model"] = await _resolve_judge_config()
        out_dict["sampled"] = sampled

        report_file = reports_dir / f"skill_ab_{benchmark_id}_{ts}.json"
        with report_file.open("w", encoding="utf-8") as f:
            json.dump(out_dict, f, indent=2, ensure_ascii=False)

        latest_file = reports_dir / "latest.json"
        if latest_file.exists():
            latest_file.unlink()
        shutil.copy2(report_file, latest_file)

        logger.info("Skill A/B evaluation completed. Report: %s", report_file)
    except Exception as exc:
        if _skill_ab_state.get("abort_requested"):
            logger.info("Skill A/B evaluation aborted by user")
        else:
            logger.exception("Skill A/B evaluation failed")
            _skill_ab_state["error"] = str(exc)
    finally:
        _skill_ab_state["is_running"] = False
        _skill_ab_state["stage"] = None
        _active_skill_ab_runner = None


def get_latest_skill_ab_report(reports_dir: Path | None = None) -> dict[str, object] | None:
    """Return the most recent Skill A/B report."""
    if reports_dir is None:
        reports_dir = DEFAULT_SKILL_AB_REPORTS_DIR
    latest_file = reports_dir / "latest.json"
    if not latest_file.exists():
        return None
    try:
        with latest_file.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def get_skill_ab_report_history(reports_dir: Path | None = None) -> list[dict[str, object]]:
    """Return all historical Skill A/B report summaries."""
    if reports_dir is None:
        reports_dir = DEFAULT_SKILL_AB_REPORTS_DIR
    if not reports_dir.exists():
        return []
    history: list[dict[str, object]] = []
    for f in sorted(reports_dir.glob("skill_ab_*.json"), reverse=True):
        if f.name == "latest.json":
            continue
        try:
            with f.open(encoding="utf-8") as fp:
                data = json.load(fp)
                history.append(
                    {
                        "filename": f.name,
                        "dataset_id": data.get("dataset_id"),
                        "candidate_skill_id": data.get("candidate_skill_id"),
                        "baseline_skill_id": data.get("baseline_skill_id"),
                        "verdict": data.get("verdict"),
                        "success_rate_delta": data.get("success_rate_delta"),
                        "created_at": data.get("created_at"),
                    }
                )
        except Exception:
            continue
    return history
