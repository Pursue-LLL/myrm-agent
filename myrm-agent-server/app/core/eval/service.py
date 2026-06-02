"""Eval Service for the Server Layer.

[INPUT]
- myrm_agent_harness.eval::EvalRunner, load_cases, JsonlReporter
- app.core.eval.executor::LocalEvalExecutor

[OUTPUT]
- run_eval_suite: runs the standard eval suite for a user.

[POS]
Orchestrates the execution of the evaluation framework within the Server layer.
Loads test cases, runs them using the user's specific Agent configuration,
and persists the results to the user's private volume.
"""

from __future__ import annotations

import asyncio
import logging
import time
from itertools import groupby
from pathlib import Path
from typing import cast

from myrm_agent_harness.eval import EvalRunner, JsonlReporter

from app.core.eval.executor import LocalEvalExecutor

logger = logging.getLogger(__name__)

# Global state for chat activity tracking (for adaptive yielding)
_last_chat_activity_time: float = 0.0


def mark_chat_activity() -> None:
    """Mark the current time as active chat activity.

    Used by the foreground ChatService to inform the background eval tasks
    to yield CPU/memory resources and avoid blocking.
    """
    global _last_chat_activity_time
    _last_chat_activity_time = time.time()


class AdaptiveEvalManager:
    """Adaptive concurrency manager that yields when chat activity is detected."""

    def __init__(self, max_concurrency: int = 3, idle_wait_seconds: float = 3.0) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._idle_wait_seconds = idle_wait_seconds

    async def __aenter__(self) -> "AdaptiveEvalManager":
        # Always yield briefly to the event loop
        await asyncio.sleep(0.01)

        # If foreground chat activity was detected recently, wait longer to yield resources
        global _last_chat_activity_time
        while time.time() - _last_chat_activity_time < self._idle_wait_seconds:
            logger.debug("Foreground chat activity detected. Suspending eval task briefly...")
            await asyncio.sleep(1.0)

        await self._semaphore.acquire()
        return self

    async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self._semaphore.release()


# Default location for saving reports
DEFAULT_REPORTS_DIR = Path(".myrm/eval_reports")
# Default location for datasets
DEFAULT_DATASETS_DIR = Path(".myrm/eval_datasets")


def _dataset_sort_key(entry: dict[str, object]) -> float:
    ts = entry.get("updated_at")
    if isinstance(ts, (int, float)):
        return float(ts)
    return 0.0


def get_dataset_path(dataset_id: str | None = None) -> Path:
    DEFAULT_DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    if not dataset_id or dataset_id == "default":
        path = DEFAULT_DATASETS_DIR / "default.jsonl"
        legacy_path = Path(".myrm/eval_cases.jsonl")
        if not path.exists() and legacy_path.exists():
            import shutil

            shutil.move(str(legacy_path), str(path))
        return path

    safe_id = "".join(c for c in dataset_id if c.isalnum() or c in ("-", "_"))
    return DEFAULT_DATASETS_DIR / f"{safe_id}.jsonl"


def get_all_datasets() -> list[dict[str, object]]:
    """List all available evaluation datasets."""
    DEFAULT_DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    datasets: list[dict[str, object]] = []

    # Ensure default exists or migrate
    get_dataset_path("default")

    for file_path in DEFAULT_DATASETS_DIR.glob("*.jsonl"):
        datasets.append(
            {
                "id": file_path.stem,
                "filename": file_path.name,
                "updated_at": file_path.stat().st_mtime,
                "size": file_path.stat().st_size,
            }
        )

    datasets.sort(key=_dataset_sort_key, reverse=True)
    return datasets


# Global state for eval execution (single-instance assumption)
_eval_state: dict[str, object] = {
    "is_running": False,
    "total": 0,
    "completed": 0,
    "error": None,
}


def get_eval_status() -> dict[str, object]:
    """Get the current status of the evaluation suite."""
    return _eval_state.copy()


_active_runner: EvalRunner | None = None


def abort_eval() -> bool:
    """Request abort of the currently running evaluation suite."""
    global _eval_state, _active_runner
    if _eval_state.get("is_running") and _active_runner:
        _active_runner.abort()
        _eval_state["error"] = "Aborted by user"
        return True
    return False


async def run_eval_suite_background(
    dataset_id: str | None = None, reports_dir: Path | None = None, profile_id: str | None = None
) -> None:
    """Run the evaluation suite in the background, updating global state."""
    global _eval_state

    if _eval_state.get("is_running"):
        logger.warning("Evaluation suite is already running. Ignoring request.")
        return

    _eval_state.clear()
    _eval_state.update(
        {
            "is_running": True,
            "total": 0,
            "completed": 0,
            "error": None,
        }
    )

    try:
        await run_eval_suite(dataset_id, reports_dir, profile_id)
    except Exception as exc:
        logger.exception("Evaluation suite failed")
        _eval_state["error"] = str(exc)
    finally:
        _eval_state["is_running"] = False


async def run_eval_suite(
    dataset_id: str | None = None, reports_dir: Path | None = None, profile_id: str | None = None
) -> dict[str, object]:
    """Run the standard evaluation suite for a user.

    Args:
        dataset_id: ID of the dataset to evaluate against.
        reports_dir: Directory where the evaluation report should be saved.
        profile_id: Optional ID of a specific Agent Profile to evaluate.

    Returns:
        A summary dictionary of the evaluation results.
    """
    cases_path = get_dataset_path(dataset_id)
    reports_dir = reports_dir or DEFAULT_REPORTS_DIR

    if not cases_path.exists():
        # Create a dummy case if none exists for testing purposes
        cases_path.parent.mkdir(parents=True, exist_ok=True)
        with cases_path.open("w", encoding="utf-8") as f:
            f.write('{"message": "Hello, world!"}\n')
            f.write('{"message": "What is 2+2?", "expected_tools": ["code_exec"]}\n')

    from myrm_agent_harness.eval import load_multi_turn_cases

    cases = load_multi_turn_cases(cases_path)

    # Group cases by profile_id to maximize LLM Prompt Cache hits
    cases.sort(key=lambda c: str(c.metadata.get("profile_id", "default")))
    grouped_cases = []
    for _, group in groupby(cases, key=lambda c: str(c.metadata.get("profile_id", "default"))):
        grouped_cases.extend(list(group))
    cases = grouped_cases

    global _eval_state, _active_runner

    # Count total turns for progress bar since it expects turns
    total_turns = sum(len(c.turns) for c in cases)
    _eval_state["total"] = total_turns
    _eval_state["completed"] = 0
    _eval_state["abort_requested"] = False

    def _on_case_complete(result: object) -> None:
        cur = _eval_state.get("completed")
        prev = int(cur) if isinstance(cur, int) else 0
        _eval_state["completed"] = prev + 1

    executor = LocalEvalExecutor(profile_id=profile_id)
    adaptive_manager = AdaptiveEvalManager(max_concurrency=3, idle_wait_seconds=3.0)
    runner = EvalRunner(executor, max_concurrency=3, on_case_complete=_on_case_complete, yielding_strategy=adaptive_manager)

    logger.info("Starting evaluation suite with %d sessions (%d turns) (Adaptive Yielding Enabled)", len(cases), total_turns)
    _active_runner = runner
    try:
        result = await runner.run_multi_turn(cases)
    finally:
        _active_runner = None

    # Save the report
    reports_dir.mkdir(parents=True, exist_ok=True)
    import time

    timestamp = int(time.time())
    report_path = reports_dir / f"eval_report_{timestamp}.jsonl"

    reporter = JsonlReporter(report_path)
    reporter.report(result)

    logger.info("Evaluation suite completed. Report saved to %s", report_path)

    # Also save a 'latest.jsonl' symlink or copy for easy access
    latest_path = reports_dir / "latest.jsonl"
    if latest_path.exists():
        latest_path.unlink()

    # Use copy instead of symlink to avoid cross-platform issues
    import shutil

    shutil.copy2(report_path, latest_path)

    return {
        "total_cases": result.total_cases,
        "pass_count": result.pass_count,
        "fail_count": result.fail_count,
        "error_count": result.error_count,
        "skip_count": result.skip_count,
        "pass_rate": result.pass_rate,
        "all_passed": result.all_passed,
        "total_ms": result.total_ms,
        "report_path": str(report_path),
    }


def get_eval_cases(dataset_id: str | None = None) -> str:
    """Get the raw content of the eval cases file."""
    cases_path = get_dataset_path(dataset_id)
    if not cases_path.exists():
        return ""
    try:
        with cases_path.open("r", encoding="utf-8") as f:
            return f.read()
    except Exception as exc:
        logger.warning("Failed to read eval cases: %s", exc)
        return ""


def save_eval_cases(content: str, dataset_id: str | None = None) -> bool:
    """Save the raw content to the eval cases file."""
    cases_path = get_dataset_path(dataset_id)
    try:
        cases_path.parent.mkdir(parents=True, exist_ok=True)
        with cases_path.open("w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception as exc:
        logger.warning("Failed to save eval cases: %s", exc)
        return False


def get_latest_report_summary(reports_dir: Path | None = None) -> dict[str, object] | None:
    """Get the summary from the latest evaluation report."""
    reports_dir = reports_dir or DEFAULT_REPORTS_DIR
    latest_path = reports_dir / "latest.jsonl"

    if not latest_path.exists():
        return None

    try:
        import json

        with latest_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
            if not lines:
                return None
            raw = json.loads(lines[0])
            if not isinstance(raw, dict):
                return None
            data = cast(dict[str, object], {str(k): v for k, v in raw.items()})
            if data.get("type") == "summary":
                cases_list: list[object] = []
                data["cases"] = cases_list
                for line in lines[1:]:
                    if line.strip():
                        cases_list.append(json.loads(line))
                return data
    except Exception as exc:
        logger.warning("Failed to read latest eval report: %s", exc)

    return None


def get_all_report_summaries(reports_dir: Path | None = None) -> list[dict[str, object]]:
    """Get summaries of all historical evaluation reports, sorted by timestamp descending."""
    reports_dir = reports_dir or DEFAULT_REPORTS_DIR
    if not reports_dir.exists():
        return []

    import json

    summaries = []
    report_files = list(reports_dir.glob("eval_report_*.jsonl"))
    report_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    for report_path in report_files:
        try:
            with report_path.open("r", encoding="utf-8") as f:
                first_line = f.readline()
                if first_line:
                    data = json.loads(first_line)
                    if data.get("type") == "summary":
                        filename = report_path.name
                        ts_str = filename.replace("eval_report_", "").replace(".jsonl", "")
                        try:
                            data["timestamp"] = int(ts_str)
                        except ValueError:
                            data["timestamp"] = int(report_path.stat().st_mtime)
                        data["filename"] = filename
                        summaries.append(data)
        except Exception as exc:
            logger.warning("Failed to read report %s: %s", report_path, exc)

    return summaries
