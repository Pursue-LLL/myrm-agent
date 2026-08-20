"""Matrix Eval — cross-profile comparative evaluation.

[INPUT]
- myrm_agent_harness.eval::MatrixRunner, AgentExecutor
- app.core.eval.datasets::get_dataset_path
- app.core.eval._state::matrix_state, active_matrix_runner, reports dir
- app.core.eval.adaptive::AdaptiveEvalManager
- app.core.eval.layered::layered-eval variants (re-exported public surface)

[OUTPUT]
- get_matrix_eval_status / abort_matrix_eval: progress query and abort.
- run_matrix_eval_background: background cross-profile matrix run.
- get_latest_matrix_report / get_matrix_report / get_matrix_report_history:
  latest reader, per-timestamp reader and history list (newest first).
- Layered eval (LayerSpec / DEFAULT_LAYER_SPECS / layer_specs_to_meta /
  run_layer_eval_background): re-exported from app.core.eval.layered.

[POS]
Evaluates the same dataset across multiple AgentProfiles sequentially and
outputs a per-profile comparison report under `.myrm/matrix_reports/`.
Layered evaluation lives in app.core.eval.layered and reuses the shared
state machine and report directory from app.core.eval._state.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path
from typing import cast

from myrm_agent_harness import __version__ as harness_version
from myrm_agent_harness.eval import AgentExecutor

from app.core.eval import _state as eval_state
from app.core.eval.adaptive import AdaptiveEvalManager
from app.core.eval.datasets import get_dataset_path
from app.core.eval.executor import LocalEvalExecutor
from app.core.eval.layered import (
    DEFAULT_LAYER_SPECS,
    LayerSpec,
    layer_specs_to_meta,
    run_layer_eval_background,
)

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_LAYER_SPECS",
    "LayerSpec",
    "abort_matrix_eval",
    "get_latest_matrix_report",
    "get_matrix_eval_status",
    "get_matrix_report",
    "get_matrix_report_history",
    "layer_specs_to_meta",
    "run_layer_eval_background",
    "run_matrix_eval_background",
]


def get_matrix_eval_status() -> dict[str, object]:
    """Get current matrix evaluation status."""
    return dict(eval_state.matrix_state)


def abort_matrix_eval() -> bool:
    """Abort the currently running matrix or layered evaluation."""
    if not eval_state.matrix_state.get("is_running"):
        return False
    # Flag so in-flight benchmark downloads (build_benchmark_cases
    # should_abort) stop early; the runner abort handles the eval phase.
    eval_state.matrix_state["abort_requested"] = True
    runner = eval_state.active_matrix_runner
    if runner is not None:
        runner.abort()
    return True


async def run_matrix_eval_background(
    dataset_id: str | None = None,
    profile_ids: list[str] | None = None,
    *,
    benchmark_mode: bool = False,
) -> None:
    """Run matrix evaluation across multiple profiles in the background."""
    if eval_state.matrix_state.get("is_running"):
        return

    eval_state.matrix_state.update(
        {
            "is_running": True,
            "current_profile": None,
            "profile_progress": 0,
            "profile_total": len(profile_ids or []),
            "case_completed": 0,
            "case_total": 0,
            "stage": "evaluating",
            "download_progress": None,
            "error": None,
            "abort_requested": False,
        }
    )

    try:
        await _run_matrix_eval(dataset_id, profile_ids, benchmark_mode=benchmark_mode)
    except Exception as exc:
        logger.exception("Matrix evaluation failed")
        eval_state.matrix_state["error"] = str(exc)
    finally:
        eval_state.matrix_state["is_running"] = False
        eval_state.matrix_state["stage"] = None
        eval_state.matrix_state["download_progress"] = None
        eval_state.active_matrix_runner = None


async def _run_matrix_eval(
    dataset_id: str | None = None,
    profile_ids: list[str] | None = None,
    *,
    benchmark_mode: bool = False,
) -> dict[str, object]:
    """Run the matrix evaluation suite."""
    from myrm_agent_harness.eval import MatrixRunner, load_multi_turn_cases

    if not profile_ids or len(profile_ids) < 2:
        raise ValueError("Matrix eval requires at least 2 profile IDs")

    cases_path = get_dataset_path(dataset_id)
    if not cases_path.exists():
        raise FileNotFoundError(f"Dataset not found: {cases_path}")

    multi_cases = load_multi_turn_cases(cases_path)
    total_turns = sum(len(mc.turns) for mc in multi_cases)

    eval_state.matrix_state["case_total"] = total_turns * len(profile_ids)

    executors: dict[str, AgentExecutor] = {}
    for pid in profile_ids:
        executors[pid] = LocalEvalExecutor(profile_id=pid, benchmark_mode=benchmark_mode)

    def _on_profile_start(profile_id: str, idx: int, total: int) -> None:
        eval_state.matrix_state["current_profile"] = profile_id
        eval_state.matrix_state["profile_progress"] = idx

    def _on_case_complete(profile_id: str, result: object) -> None:
        cur = eval_state.matrix_state.get("case_completed")
        prev = int(cur) if isinstance(cur, int) else 0
        eval_state.matrix_state["case_completed"] = prev + 1

    adaptive_manager = AdaptiveEvalManager(max_concurrency=3, idle_wait_seconds=3.0)

    # Disclose the judge model so scores stay traceable after the user
    # switches models. Matrix datasets may carry LLM-judge assertions
    # (semantic grading), so the resolved judge credentials are injected into
    # the runner for a consistent grading model — matching the memory_ab and
    # layered report disclosure.
    from app.core.eval.model_config import _resolve_judge_config

    judge_config, judge_model = await _resolve_judge_config()

    runner = MatrixRunner(
        executors,
        max_concurrency_per_profile=3,
        on_profile_start=_on_profile_start,
        on_case_complete=_on_case_complete,
        yielding_strategy=adaptive_manager,
        judge_config=judge_config,
    )
    eval_state.active_matrix_runner = runner
    try:
        matrix_result = await runner.run_multi_turn(multi_cases)
    finally:
        eval_state.active_matrix_runner = None
        # Remove per-case session workspaces so matrix eval never leaves
        # throwaway directories behind (success, error, or abort).  Each
        # cleanup is guarded independently so one profile's failure cannot
        # skip the rest.
        for eval_executor in executors.values():
            try:
                await eval_executor.cleanup()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to clean matrix eval workspaces: %s", exc)

    eval_state.matrix_state["profile_progress"] = len(profile_ids)

    reports_dir = eval_state.DEFAULT_MATRIX_REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)

    timestamp = int(time.time())
    report_path = reports_dir / f"matrix_report_{timestamp}.json"

    report_data = matrix_result.to_dict()
    report_data["timestamp"] = timestamp
    report_data["dataset_id"] = dataset_id or "default"
    report_data["eval_type"] = "matrix"
    report_data["harness_version"] = harness_version
    report_data["benchmark_mode"] = benchmark_mode
    # Disclose the judge model used for any LLM-judge assertions so a later
    # score change caused by switching the user's model stays traceable
    # (same disclosure as memory_ab and layered reports).
    report_data["judge_model"] = judge_model
    # A user abort mid-run leaves partial results: mark the report so it is
    # never mistaken for a complete run in the Eval Lab history.
    report_data["aborted"] = bool(eval_state.matrix_state.get("abort_requested"))

    # Each profile may pin a different model; disclose the per-profile label
    # so the report stays self-contained regardless of later profile changes.
    from app.core.eval.model_config import _resolve_agent_model_label

    per_profile = report_data.get("per_profile")
    if isinstance(per_profile, dict):
        for pid in profile_ids:
            profile_summary = per_profile.get(pid)
            if isinstance(profile_summary, dict):
                profile_summary["agent_model"] = await _resolve_agent_model_label(pid)

    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    latest_path = reports_dir / "latest.json"
    if latest_path.exists():
        latest_path.unlink()
    shutil.copy2(report_path, latest_path)

    logger.info("Matrix evaluation completed. Report: %s", report_path)
    return report_data


def get_latest_matrix_report() -> dict[str, object] | None:
    """Get the latest matrix evaluation report."""
    latest_path = eval_state.DEFAULT_MATRIX_REPORTS_DIR / "latest.json"
    if not latest_path.exists():
        return None
    try:
        with latest_path.open("r", encoding="utf-8") as f:
            return cast(dict[str, object], json.load(f))
    except Exception as exc:
        logger.warning("Failed to read matrix report: %s", exc)
        return None


def get_matrix_report(timestamp: int) -> dict[str, object] | None:
    """Get a specific matrix/layered report by its run timestamp."""
    report_path = eval_state.DEFAULT_MATRIX_REPORTS_DIR / f"matrix_report_{timestamp}.json"
    if not report_path.exists():
        return None
    try:
        with report_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            logger.warning("Matrix report %s is not an object", report_path)
            return None
        return data
    except Exception as exc:
        logger.warning("Failed to read matrix report %s: %s", report_path, exc)
        return None


def _matrix_report_sort_key(item: dict[str, object]) -> int:
    """Sort key for report summaries: run timestamp, missing treated as 0."""
    ts = item.get("timestamp")
    return ts if isinstance(ts, int) else 0


def get_matrix_report_history(
    reports_dir: Path | None = None,
) -> list[dict[str, object]]:
    """Get all matrix/layered reports, newest first.

    Returns a lightweight summary per run (timestamp, dataset, type, models)
    so the UI can show a history list without shipping the full per-case matrix.
    """
    reports_dir = reports_dir or eval_state.DEFAULT_MATRIX_REPORTS_DIR
    if not reports_dir.exists():
        return []

    summaries: list[dict[str, object]] = []
    for report_path in reports_dir.glob("matrix_report_*.json"):
        try:
            with report_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                continue
            summaries.append(
                {
                    "timestamp": data.get("timestamp"),
                    "dataset_id": data.get("dataset_id"),
                    "profile_id": data.get("profile_id"),
                    "eval_type": data.get("eval_type"),
                    "judge_model": data.get("judge_model"),
                    "agent_model": data.get("agent_model"),
                    "stable_rate": data.get("stable_rate"),
                    "limit": data.get("limit"),
                    "aborted": data.get("aborted", False),
                }
            )
        except Exception as exc:
            logger.warning("Failed to read matrix report %s: %s", report_path, exc)

    summaries.sort(key=_matrix_report_sort_key, reverse=True)
    return summaries
