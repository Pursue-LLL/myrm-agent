"""Matrix Eval — cross-profile comparative evaluation.

[INPUT]
- myrm_agent_harness.eval::MatrixRunner, AgentExecutor
- app.core.eval.datasets::get_dataset_path
- app.core.eval.reports::DEFAULT_REPORTS_DIR
- app.core.eval.adaptive::AdaptiveEvalManager

[OUTPUT]
- get_matrix_eval_status / abort_matrix_eval: progress query and abort.
- run_matrix_eval_background: background cross-profile matrix run.
- get_latest_matrix_report: latest report reader.

[POS]
Evaluates the same dataset across multiple AgentProfiles sequentially and
outputs a per-profile comparison report under `.myrm/matrix_reports/`.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from typing import TYPE_CHECKING, cast

from myrm_agent_harness.eval import AgentExecutor

from app.core.eval.adaptive import AdaptiveEvalManager
from app.core.eval.datasets import get_dataset_path
from app.core.eval.executor import LocalEvalExecutor
from app.core.eval.reports import DEFAULT_REPORTS_DIR

if TYPE_CHECKING:
    from myrm_agent_harness.eval import MatrixRunner

logger = logging.getLogger(__name__)

_matrix_state: dict[str, object] = {
    "is_running": False,
    "current_profile": None,
    "profile_progress": 0,
    "profile_total": 0,
    "case_completed": 0,
    "case_total": 0,
    "error": None,
}

_active_matrix_runner: "MatrixRunner | None" = None

DEFAULT_MATRIX_REPORTS_DIR = DEFAULT_REPORTS_DIR.parent / "matrix_reports"


def get_matrix_eval_status() -> dict[str, object]:
    """Get current matrix evaluation status."""
    return dict(_matrix_state)


def abort_matrix_eval() -> bool:
    """Abort the currently running matrix evaluation."""
    global _active_matrix_runner
    if not _matrix_state.get("is_running"):
        return False
    if _active_matrix_runner:
        _active_matrix_runner.abort()
    return True


async def run_matrix_eval_background(
    dataset_id: str | None = None,
    profile_ids: list[str] | None = None,
    *,
    benchmark_mode: bool = False,
) -> None:
    """Run matrix evaluation across multiple profiles in the background."""
    global _matrix_state, _active_matrix_runner

    if _matrix_state.get("is_running"):
        return

    _matrix_state.update(
        {
            "is_running": True,
            "current_profile": None,
            "profile_progress": 0,
            "profile_total": len(profile_ids or []),
            "case_completed": 0,
            "case_total": 0,
            "error": None,
        }
    )

    try:
        await _run_matrix_eval(dataset_id, profile_ids, benchmark_mode=benchmark_mode)
    except Exception as exc:
        logger.exception("Matrix evaluation failed")
        _matrix_state["error"] = str(exc)
    finally:
        _matrix_state["is_running"] = False
        _active_matrix_runner = None


async def _run_matrix_eval(
    dataset_id: str | None = None,
    profile_ids: list[str] | None = None,
    *,
    benchmark_mode: bool = False,
) -> dict[str, object]:
    """Run the matrix evaluation suite."""
    global _matrix_state, _active_matrix_runner

    from myrm_agent_harness.eval import MatrixRunner, load_multi_turn_cases

    if not profile_ids or len(profile_ids) < 2:
        raise ValueError("Matrix eval requires at least 2 profile IDs")

    cases_path = get_dataset_path(dataset_id)
    if not cases_path.exists():
        raise FileNotFoundError(f"Dataset not found: {cases_path}")

    multi_cases = load_multi_turn_cases(cases_path)
    total_turns = sum(len(mc.turns) for mc in multi_cases)

    _matrix_state["case_total"] = total_turns * len(profile_ids)

    executors: dict[str, AgentExecutor] = {}
    for pid in profile_ids:
        executors[pid] = LocalEvalExecutor(
            profile_id=pid, benchmark_mode=benchmark_mode
        )

    def _on_profile_start(profile_id: str, idx: int, total: int) -> None:
        _matrix_state["current_profile"] = profile_id
        _matrix_state["profile_progress"] = idx

    def _on_case_complete(profile_id: str, result: object) -> None:
        cur = _matrix_state.get("case_completed")
        prev = int(cur) if isinstance(cur, int) else 0
        _matrix_state["case_completed"] = prev + 1

    adaptive_manager = AdaptiveEvalManager(max_concurrency=3, idle_wait_seconds=3.0)
    runner = MatrixRunner(
        executors,
        max_concurrency_per_profile=3,
        on_profile_start=_on_profile_start,
        on_case_complete=_on_case_complete,
        yielding_strategy=adaptive_manager,
    )
    _active_matrix_runner = runner

    try:
        matrix_result = await runner.run_multi_turn(multi_cases)
    finally:
        _active_matrix_runner = None
        # Remove per-case session workspaces so matrix eval never leaves
        # throwaway directories behind (success, error, or abort).
        for eval_executor in executors.values():
            await eval_executor.cleanup()

    _matrix_state["profile_progress"] = len(profile_ids)

    reports_dir = DEFAULT_MATRIX_REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)

    timestamp = int(time.time())
    report_path = reports_dir / f"matrix_report_{timestamp}.json"

    report_data = matrix_result.to_dict()
    report_data["timestamp"] = timestamp
    report_data["dataset_id"] = dataset_id or "default"
    report_data["benchmark_mode"] = benchmark_mode

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
    latest_path = DEFAULT_MATRIX_REPORTS_DIR / "latest.json"
    if not latest_path.exists():
        return None
    try:
        with latest_path.open("r", encoding="utf-8") as f:
            return cast(dict[str, object], json.load(f))
    except Exception as exc:
        logger.warning("Failed to read matrix report: %s", exc)
        return None
