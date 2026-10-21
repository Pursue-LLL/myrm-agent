"""Skill A/B Evaluation — No-Skill vs Baseline-Skill vs Candidate-Skill three-arm comparative evaluation.

[INPUT]
- myrm_agent_harness.eval::MatrixRunner, AgentExecutor, SkillABReportData, SkillABArmMetrics
- app.core.eval.reports::DEFAULT_REPORTS_DIR
- app.core.eval.adaptive::AdaptiveEvalManager
- app.core.eval.model_config::_resolve_agent_model_label / _resolve_judge_config
- app.core.eval.benchmarks::build_benchmark_cases, benchmark_* helpers (same as memory_ab)

[OUTPUT]
- get_skill_ab_status / abort_skill_ab: Progress query and abort control.
- run_skill_ab_background: Background three-arm evaluation run.
- get_latest_skill_ab_report / get_skill_ab_report / get_skill_ab_report_history.

[POS]
Reuses MatrixRunner with three executors differing strictly in their skill set:
1. no_skill: skill_ids_override = []
2. baseline: skill_ids_override = [baseline_skill_id] (or empty if none)
3. candidate: skill_ids_override = [candidate_skill_id]
Orchestration matches app.core.eval.memory_ab (run_multi_turn + AdaptiveEvalManager).
"""

from __future__ import annotations

import asyncio
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
    EvalResult,
    SkillABArmMetrics,
    SkillABReportData,
    calculate_paired_significance,
)
from myrm_agent_harness.eval.significance import SignificanceVerdict

from app.core.eval.adaptive import AdaptiveEvalManager
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
            "download_progress": {"downloaded_bytes": 0, "total_bytes": 0},
        }
    )


def _report_skill_ab_download_progress(downloaded: int, total: int) -> None:
    _skill_ab_state["download_progress"] = {
        "downloaded_bytes": downloaded,
        "total_bytes": total,
    }


def _skill_ab_abort_requested() -> bool:
    return bool(_skill_ab_state.get("abort_requested"))


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


def _verdict_from_significance(assessment_verdict: SignificanceVerdict) -> str:
    if assessment_verdict in (
        SignificanceVerdict.SIGNIFICANT_IMPROVEMENT,
        SignificanceVerdict.EFFICIENCY_BREAKTHROUGH,
    ):
        return "IMPROVED"
    if assessment_verdict == SignificanceVerdict.SIGNIFICANT_REGRESSION:
        return "REGRESSED"
    if assessment_verdict == SignificanceVerdict.NO_SIGNIFICANT_DIFFERENCE:
        return "EQUIVALENT"
    return "INCONCLUSIVE"


def _arm_metrics(arm_name: str, skill_id: str | None, arm_res: EvalResult | None, case_count: int) -> SkillABArmMetrics:
    if arm_res is None:
        return SkillABArmMetrics(
            arm_name=arm_name,
            skill_id=skill_id,
            pass_count=0,
            total_cases=case_count,
            pass_rate=0.0,
            avg_tool_calls=0.0,
            total_tokens=0,
            avg_latency_ms=0.0,
        )

    turn_results = arm_res.turn_results
    total_tool_calls = sum(len(t.response.tools_called) for t in turn_results)
    avg_tools = round(total_tool_calls / max(1, len(turn_results)), 2)
    total_lat = sum(t.timings.total_ms for t in turn_results)
    avg_lat = round(total_lat / max(1, len(turn_results)), 2)

    return SkillABArmMetrics(
        arm_name=arm_name,
        skill_id=skill_id,
        pass_count=arm_res.pass_count,
        total_cases=arm_res.total_cases or case_count,
        pass_rate=round(arm_res.pass_rate, 4),
        avg_tool_calls=avg_tools,
        total_tokens=arm_res.total_tokens,
        avg_latency_ms=avg_lat,
    )


def _paired_outcomes(matrix_result: object, base_id: str, cand_id: str) -> tuple[list[bool], list[bool], list[int], list[int], list[float], list[float], list[float], list[float]]:
    """Extract aligned per-case metrics for McNemar (uses MatrixResult cells)."""
    extract = getattr(matrix_result, "_extract_profile_metrics", None)
    if not callable(extract):
        return [], [], [], [], [], [], [], []
    b_out, b_tok, b_cost, b_ms = extract(base_id)
    c_out, c_tok, c_cost, c_ms = extract(cand_id)
    return b_out, c_out, b_tok, c_tok, b_cost, c_cost, b_ms, c_ms


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
    executors: dict[str, AgentExecutor] = {}

    try:
        from app.core.eval.benchmarks import (
            benchmark_decontam,
            benchmark_needs_judge,
            benchmark_required_tools,
            benchmark_run_limits,
            build_benchmark_cases,
        )
        from app.core.eval.model_config import (
            _resolve_agent_model_label,
            _resolve_judge_config,
        )

        cases, seed_map, sampled = await asyncio.to_thread(
            build_benchmark_cases,
            benchmark_id,
            limit=limit,
            progress_callback=_report_skill_ab_download_progress,
            should_abort=_skill_ab_abort_requested,
        )
        if _skill_ab_abort_requested():
            logger.info("Skill A/B aborted by user before evaluation")
            return

        if not cases:
            _skill_ab_state["error"] = f"Benchmark '{benchmark_id}' contains no eval cases."
            return

        _skill_ab_state["stage"] = "evaluating"
        total_turns = sum(len(mc.turns) for mc in cases)
        _skill_ab_state["case_total"] = total_turns * 3

        judge_config = None
        judge_model = "none"
        if benchmark_needs_judge(benchmark_id):
            judge_config, judge_model = await _resolve_judge_config()

        benchmark_tools = benchmark_required_tools(benchmark_id)
        max_tool_calls, max_iterations = benchmark_run_limits(benchmark_id)
        blocked_hostnames, blocked_terms = benchmark_decontam(benchmark_id)

        def _executor(skill_ids: list[str]) -> LocalEvalExecutor:
            return LocalEvalExecutor(
                benchmark_mode=True,
                benchmark_tools=benchmark_tools,
                max_tool_calls=max_tool_calls,
                max_iterations=max_iterations,
                blocked_hostnames=blocked_hostnames,
                blocked_terms=blocked_terms,
                skill_ids_override=skill_ids,
                workspace_seed_map=seed_map,
            )

        executors = {
            "no_skill": _executor([]),
            "baseline": _executor([baseline_skill_id] if baseline_skill_id else []),
            "candidate": _executor([candidate_skill_id]),
        }

        from myrm_agent_harness.eval import MatrixRunner

        def _on_arm_start(arm_id: str, idx: int, _total: int) -> None:
            _skill_ab_state["current_arm"] = arm_id
            _skill_ab_state["profile_progress"] = idx

        def _on_case_complete(_arm_id: str, _result: object) -> None:
            cur = _skill_ab_state.get("case_completed")
            prev = int(cur) if isinstance(cur, int) else 0
            _skill_ab_state["case_completed"] = prev + 1

        adaptive_manager = AdaptiveEvalManager(max_concurrency=3, idle_wait_seconds=3.0)
        runner = MatrixRunner(
            executors,
            max_concurrency_per_profile=3,
            on_profile_start=_on_arm_start,
            on_case_complete=_on_case_complete,
            yielding_strategy=adaptive_manager,
            judge_config=judge_config,
        )
        _active_skill_ab_runner = runner
        try:
            matrix_result = await runner.run_multi_turn(cases)
        finally:
            _active_skill_ab_runner = None

        _skill_ab_state["profile_progress"] = 3

        case_count = len(cases)
        no_skill_m = _arm_metrics(
            "no_skill",
            None,
            matrix_result.per_profile_results.get("no_skill"),
            case_count,
        )
        base_m = _arm_metrics(
            "baseline",
            baseline_skill_id,
            matrix_result.per_profile_results.get("baseline"),
            case_count,
        )
        cand_m = _arm_metrics(
            "candidate",
            candidate_skill_id,
            matrix_result.per_profile_results.get("candidate"),
            case_count,
        )

        ref_arm_name = "baseline" if baseline_skill_id else "no_skill"
        ref_m = base_m if baseline_skill_id else no_skill_m
        succ_delta = cand_m.pass_rate - ref_m.pass_rate

        token_savings = 0.0
        if ref_m.total_tokens > 0:
            token_savings = (ref_m.total_tokens - cand_m.total_tokens) / ref_m.total_tokens

        step_red = 0.0
        if ref_m.avg_tool_calls > 0:
            step_red = (ref_m.avg_tool_calls - cand_m.avg_tool_calls) / ref_m.avg_tool_calls

        b_out, c_out, b_tok, c_tok, b_cost, c_cost, b_ms, c_ms = _paired_outcomes(
            matrix_result,
            ref_arm_name,
            "candidate",
        )
        assessment = calculate_paired_significance(
            b_out,
            c_out,
            base_id=ref_arm_name,
            candidate_id="candidate",
            base_tokens=b_tok,
            candidate_tokens=c_tok,
            base_costs=b_cost,
            candidate_costs=c_cost,
            base_ms=b_ms,
            candidate_ms=c_ms,
        )
        verdict = _verdict_from_significance(assessment.verdict)

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
        out_dict["judge_model"] = judge_model
        out_dict["sampled"] = sampled
        out_dict["limit"] = limit if sampled else None
        out_dict["harness_version"] = harness_version
        out_dict["max_tool_calls"] = max_tool_calls
        out_dict["max_iterations"] = max_iterations
        out_dict["decontam_active"] = bool(blocked_hostnames or blocked_terms)
        out_dict["aborted"] = bool(_skill_ab_state.get("abort_requested"))
        out_dict["paired_significance"] = assessment.to_dict()

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
        for eval_executor in executors.values():
            try:
                await eval_executor.cleanup()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to clean skill A/B eval workspaces: %s", exc)


def get_latest_skill_ab_report(
    reports_dir: Path | None = None,
) -> dict[str, object] | None:
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


def get_skill_ab_report_history(
    reports_dir: Path | None = None,
) -> list[dict[str, object]]:
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
