"""Eval Service for the Server Layer.

[INPUT]
- myrm_agent_harness.eval::EvalRunner, load_cases, JsonlReporter
- app.core.eval.executor::LocalEvalExecutor

[OUTPUT]
- run_eval_suite: runs the standard eval suite for a user.
- run_wb_bench_background / run_wb_bench_download_background: WorkBuddy Bench
  subset run and download-only flows with progress via _eval_state.

[POS]
Orchestrates the execution of the evaluation framework within the Server layer.
Loads test cases, runs them using the user's specific Agent configuration,
and persists the results to the user's private volume.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from itertools import groupby
from pathlib import Path
from typing import TYPE_CHECKING, cast

from myrm_agent_harness.eval import EvalManifest, EvalRunner, JsonlReporter

from app.core.eval.executor import LocalEvalExecutor

if TYPE_CHECKING:
    from myrm_agent_harness.eval import MatrixRunner, MultiTurnEvalCase

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


def _report_wb_bench_download_progress(downloaded: int, total: int) -> None:
    """Record the current WorkBuddy Bench download progress into global state.

    Called from the download stream (potentially a worker thread for the run
    flow); plain dict item assignment is atomic under the GIL, and the SSE
    generator snapshots the dict, so the update is safe without a lock.
    """
    _eval_state["download_progress"] = {
        "downloaded_bytes": downloaded,
        "total_bytes": total,
    }


def _wb_bench_abort_requested() -> bool:
    """Report whether the user requested abort of the current download."""
    return bool(_eval_state.get("abort_requested"))


def _init_wb_bench_state(subset_id: str) -> None:
    """Reset global eval state for a WBBench background flow (run or download-only)."""
    _eval_state.clear()
    _eval_state.update(
        {
            "is_running": True,
            "total": 0,
            "completed": 0,
            "error": None,
            "abort_requested": False,
            "stage": "downloading",
            "stage_subset_id": subset_id,
            "download_progress": {"downloaded_bytes": 0, "total_bytes": 0},
        }
    )


def _reset_wb_bench_state() -> None:
    """Clear run flags and stage markers when a WBBench flow finishes."""
    _eval_state["is_running"] = False
    _eval_state["stage"] = None
    _eval_state["stage_subset_id"] = None


def get_eval_status() -> dict[str, object]:
    """Get the current status of the evaluation suite."""
    return _eval_state.copy()


_active_runner: EvalRunner | None = None


def abort_eval() -> bool:
    """Request abort of the currently running evaluation suite.

    For a live run this aborts the active runner; during the WBBench download
    phase (no runner yet) it sets ``abort_requested`` so the stream loop stops.
    """
    global _eval_state, _active_runner
    if not _eval_state.get("is_running"):
        return False
    _eval_state["abort_requested"] = True
    if _active_runner:
        _active_runner.abort()
        _eval_state["error"] = "Aborted by user"
    return True


async def _build_eval_manifest(
    profile_id: str | None,
    dataset_id: str,
    cases_path: Path,
    *,
    benchmark_mode: bool = False,
    external_cases: list["MultiTurnEvalCase"] | None = None,
) -> EvalManifest:
    """Build an EvalManifest capturing the current evaluation environment."""
    import hashlib
    from datetime import datetime, timezone

    import myrm_agent_harness

    from app.core.channel_bridge.config_loader import load_user_configs

    configs = await load_user_configs()

    model_provider = "unknown"
    model_id = "unknown"
    budget_max_tokens = 4096
    thinking_effort = "default"
    tool_policy: list[str] = []
    prompt_fingerprint = "none"

    if profile_id:
        from app.services.agent.profile_resolver import get_agent_profile_resolver

        resolved = await get_agent_profile_resolver().resolve(profile_id)
        if resolved:
            if resolved.model:
                parts = resolved.model.split("/", 1)
                if len(parts) == 2:
                    model_provider, model_id = parts
                else:
                    model_id = resolved.model
            if resolved.engine_params:
                thinking_effort = str(resolved.engine_params.get("thinking_effort", "default"))
                budget_max_tokens = int(resolved.engine_params.get("max_tokens", budget_max_tokens))
            tool_policy = list(resolved.enabled_builtin_tools)
            if resolved.system_prompt:
                prompt_fingerprint = hashlib.sha256(
                    resolved.system_prompt.encode("utf-8")
                ).hexdigest()

    if model_id == "unknown" and configs.model_cfg:
        model_id = str(getattr(configs.model_cfg, "model", "unknown"))
        raw_model = model_id
        parts = raw_model.split("/", 1)
        if len(parts) == 2:
            model_provider, model_id = parts


    task_set_hash = "empty"
    if cases_path.exists():
        content = cases_path.read_bytes()
        task_set_hash = hashlib.sha256(content).hexdigest()
    else:
        import pickle

        try:
            task_set_hash = hashlib.sha256(pickle.dumps(external_cases)).hexdigest()
        except Exception:  # noqa: BLE001 - fall back to a stable marker on any serialization edge case
            task_set_hash = f"external-{dataset_id}"

    return EvalManifest(
        model_provider=model_provider,
        model_id=model_id,
        thinking_effort=thinking_effort,
        harness_version=myrm_agent_harness.__version__,
        tool_policy=tuple(tool_policy),
        task_set_id=dataset_id,
        task_set_hash=task_set_hash,
        prompt_fingerprint=prompt_fingerprint,
        budget_max_tokens=budget_max_tokens,
        timeout_seconds=300,
        created_at=datetime.now(timezone.utc).isoformat(),
        profile_id=profile_id or "default",
        benchmark_mode=benchmark_mode,
    )


async def run_eval_suite_background(
    dataset_id: str | None = None,
    reports_dir: Path | None = None,
    profile_id: str | None = None,
    *,
    benchmark_mode: bool = False,
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
        await run_eval_suite(
            dataset_id, reports_dir, profile_id, benchmark_mode=benchmark_mode
        )
    except Exception as exc:
        logger.exception("Evaluation suite failed")
        _eval_state["error"] = str(exc)
    finally:
        _eval_state["is_running"] = False


async def run_wb_bench_background(
    subset_id: str,
    reports_dir: Path | None = None,
    profile_id: str | None = None,
    *,
    benchmark_mode: bool = False,
) -> None:
    """Run a WorkBuddy Bench subset in the background, updating global eval state."""
    global _eval_state

    # The router marks is_running synchronously before scheduling this task so
    # the SSE stream opened on "started" never reads a stale idle first frame.
    # If the state was not pre-initialized (direct/legacy callers), do it here.
    if not _eval_state.get("is_running"):
        _init_wb_bench_state(subset_id)

    try:
        from app.core.eval.wb_bench import build_wb_bench_cases

        cases, seed_map = await asyncio.to_thread(
            build_wb_bench_cases,
            subset_id,
            progress_callback=_report_wb_bench_download_progress,
            should_abort=_wb_bench_abort_requested,
        )
        # An abort during the download/extract worker phase is only visible
        # after the thread returns; never start evaluating after a cancel.
        if _eval_state.get("abort_requested"):
            logger.info("WBBench evaluation aborted by user before evaluation")
            return
        _eval_state["stage"] = "evaluating"
        dataset_id = f"wb-bench-{subset_id}"
        await run_eval_suite(
            dataset_id=dataset_id,
            reports_dir=reports_dir,
            profile_id=profile_id,
            benchmark_mode=benchmark_mode,
            external_cases=cases,
            workspace_seed_map=seed_map,
        )
    except Exception as exc:
        if _eval_state.get("abort_requested"):
            logger.info("WBBench evaluation aborted by user")
        else:
            logger.exception("WBBench evaluation suite failed")
            _eval_state["error"] = str(exc)
    finally:
        _reset_wb_bench_state()


async def run_wb_bench_download_background(subset_id: str) -> None:
    """Download a WorkBuddy Bench subset in the background (download-only flow).

    Reuses the same global eval state and SSE stream as a full run so the UI
    can show live download progress; no evaluation is scheduled.
    """
    global _eval_state

    if not _eval_state.get("is_running"):
        _init_wb_bench_state(subset_id)

    try:
        from app.core.eval.wb_bench import ensure_wb_bench_source

        await ensure_wb_bench_source(
            subset_id,
            progress_callback=_report_wb_bench_download_progress,
            should_abort=_wb_bench_abort_requested,
        )
    except Exception as exc:
        if _eval_state.get("abort_requested"):
            logger.info("WBBench download aborted by user")
        else:
            logger.exception("WBBench download failed")
            _eval_state["error"] = str(exc)
    finally:
        _reset_wb_bench_state()


async def run_eval_suite(
    dataset_id: str | None = None,
    reports_dir: Path | None = None,
    profile_id: str | None = None,
    *,
    benchmark_mode: bool = False,
    external_cases: list["MultiTurnEvalCase"] | None = None,
    workspace_seed_map: dict[str, str] | None = None,
) -> dict[str, object]:
    """Run the standard evaluation suite for a user.

    Args:
        dataset_id: ID of the dataset to evaluate against.
        reports_dir: Directory where the evaluation report should be saved.
        profile_id: Optional ID of a specific Agent Profile to evaluate.
        benchmark_mode: When True, strips all user-specific configuration
            to produce a clean, fair baseline for harness-level benchmarks.
        external_cases: Optional pre-built cases (e.g. WorkBuddy Bench) that
            bypass the JSONL dataset loading step.
        workspace_seed_map: Maps a case message to a pre-provisioned workspace
            directory that is copied into the session workspace before the
            agent runs (used by external dataset adapters).

    Returns:
        A summary dictionary of the evaluation results.
    """
    cases_path = get_dataset_path(dataset_id)
    reports_dir = reports_dir or DEFAULT_REPORTS_DIR

    if external_cases is not None:
        cases = external_cases
    else:
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

    executor = LocalEvalExecutor(
        profile_id=profile_id,
        benchmark_mode=benchmark_mode,
        workspace_seed_map=workspace_seed_map,
    )
    adaptive_manager = AdaptiveEvalManager(max_concurrency=3, idle_wait_seconds=3.0)
    runner = EvalRunner(executor, max_concurrency=3, on_case_complete=_on_case_complete, yielding_strategy=adaptive_manager)

    manifest = await _build_eval_manifest(
        profile_id=profile_id,
        dataset_id=dataset_id or "default",
        cases_path=cases_path,
        benchmark_mode=benchmark_mode,
        external_cases=external_cases,
    )

    logger.info("Starting evaluation suite with %d sessions (%d turns) (Adaptive Yielding Enabled)", len(cases), total_turns)
    _active_runner = runner
    try:
        result = await runner.run_multi_turn(cases, manifest=manifest)
    finally:
        _active_runner = None

    # Save the report
    reports_dir.mkdir(parents=True, exist_ok=True)

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
        "manifest": manifest.to_dict(),
        **({"avg_pass_rate": result.avg_pass_rate} if result.avg_pass_rate is not None else {}),
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


# ---------------------------------------------------------------------------
# Matrix Eval — cross-profile comparative evaluation
# ---------------------------------------------------------------------------

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

    _matrix_state.update({
        "is_running": True,
        "current_profile": None,
        "profile_progress": 0,
        "profile_total": len(profile_ids or []),
        "case_completed": 0,
        "case_total": 0,
        "error": None,
    })

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

    executors: dict[str, LocalEvalExecutor] = {}
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
            return json.load(f)
    except Exception as exc:
        logger.warning("Failed to read matrix report: %s", exc)
        return None
