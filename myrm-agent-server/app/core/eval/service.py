"""Eval Service for the Server Layer.

[INPUT]
- myrm_agent_harness.eval::EvalRunner, JsonlReporter
- app.core.eval.manifest::_build_eval_manifest (POS: 构建评测环境快照，含模型/tool policy/指纹/抽样披露)
- app.core.eval.model_config::_resolve_agent_model_label / _resolve_judge_config (POS: 统一模型解析与 judge 注入)
- app.core.eval.executor::LocalEvalExecutor
- app.core.eval.adaptive::AdaptiveEvalManager
- app.core.eval.datasets::get_dataset_path
- app.core.eval.reports::DEFAULT_REPORTS_DIR

[OUTPUT]
- run_eval_suite: runs the standard eval suite for a user.
- run_eval_suite_background: background wrapper with progress via _eval_state.
- run_benchmark_background / run_benchmark_download_background: generic
  benchmark run and download-only flows (WBBench subsets + registered
  third-party benchmarks) with progress via _eval_state.
- run_wb_bench_background / run_wb_bench_download_background: legacy
  WorkBuddy Bench entry points delegating to the generic flows.

[POS]
Orchestrates the execution of the evaluation framework within the Server layer.
Loads test cases, runs them using the user's specific Agent configuration,
and persists the results to the user's private volume.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from itertools import groupby
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.eval import (
    EvalRunner,
    JsonlReporter,
)

from app.core.eval.adaptive import AdaptiveEvalManager
from app.core.eval.datasets import get_dataset_path
from app.core.eval.executor import LocalEvalExecutor
from app.core.eval.manifest import _build_eval_manifest
from app.core.eval.model_config import _resolve_judge_config
from app.core.eval.reports import DEFAULT_REPORTS_DIR

if TYPE_CHECKING:
    from myrm_agent_harness.eval import MultiTurnEvalCase

logger = logging.getLogger(__name__)


# Global state for eval execution (single-instance assumption)
_eval_state: dict[str, object] = {
    "is_running": False,
    "total": 0,
    "completed": 0,
    "error": None,
}


def _report_benchmark_download_progress(downloaded: int, total: int) -> None:
    """Record the current WorkBuddy Bench download progress into global state.

    Called from the download stream (potentially a worker thread for the run
    flow); plain dict item assignment is atomic under the GIL, and the SSE
    generator snapshots the dict, so the update is safe without a lock.
    """
    _eval_state["download_progress"] = {
        "downloaded_bytes": downloaded,
        "total_bytes": total,
    }


def _benchmark_abort_requested() -> bool:
    """Report whether the user requested abort of the current download."""
    return bool(_eval_state.get("abort_requested"))


def _init_benchmark_state(stage_label: str) -> None:
    """Reset global eval state for an external benchmark background flow.

    ``stage_label`` is the handle shown in the SSE stream (a WBBench subset id
    or a third-party benchmark id); the run/download flows share this state.
    """
    _eval_state.clear()
    _eval_state.update(
        {
            "is_running": True,
            "total": 0,
            "completed": 0,
            "error": None,
            "abort_requested": False,
            "stage": "downloading",
            "stage_subset_id": stage_label,
            "download_progress": {"downloaded_bytes": 0, "total_bytes": 0},
        }
    )


def _reset_benchmark_state() -> None:
    """Clear run flags and stage markers when a benchmark flow finishes."""
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
        await run_eval_suite(dataset_id, reports_dir, profile_id, benchmark_mode=benchmark_mode)
    except Exception as exc:
        logger.exception("Evaluation suite failed")
        _eval_state["error"] = str(exc)
    finally:
        _eval_state["is_running"] = False


async def run_benchmark_background(
    benchmark_id: str,
    reports_dir: Path | None = None,
    profile_id: str | None = None,
    *,
    benchmark_mode: bool = False,
    stage_label: str | None = None,
    limit: int | None = None,
) -> None:
    """Run an external benchmark (WBBench subset or registered third-party).

    Resolves the benchmark through ``benchmarks`` (WBBench subsets or the
    framework registry), downloads if needed, builds runnable cases, and runs
    the eval suite with the benchmark's declared tool whitelist. ``stage_label``
    overrides the SSE ``stage_subset_id`` (WBBench keeps its bare subset id for
    existing frontend compatibility). ``limit`` caps the case count (random
    sample, reproducible).
    """
    global _eval_state

    # The router marks is_running synchronously before scheduling this task so
    # the SSE stream opened on "started" never reads a stale idle first frame.
    # If the state was not pre-initialized (direct/legacy callers), do it here.
    if not _eval_state.get("is_running"):
        _init_benchmark_state(stage_label or benchmark_id)

    try:
        from app.core.eval.benchmarks import (
            benchmark_decontam,
            benchmark_required_tools,
            benchmark_run_limits,
            build_benchmark_cases,
        )

        cases, seed_map, sampled = await asyncio.to_thread(
            build_benchmark_cases,
            benchmark_id,
            limit=limit,
            progress_callback=_report_benchmark_download_progress,
            should_abort=_benchmark_abort_requested,
        )
        # An abort during the download/extract worker phase is only visible
        # after the thread returns; never start evaluating after a cancel.
        if _eval_state.get("abort_requested"):
            logger.info("Benchmark %s aborted by user before evaluation", benchmark_id)
            return
        _eval_state["stage"] = "evaluating"
        # The manifest records the sample size only when a sample was actually
        # drawn (limit < full case count); a limit at/above the full count is
        # a full run and must not be flagged as sampled.
        sample_size = limit if sampled else None
        max_tool_calls, max_iterations = benchmark_run_limits(benchmark_id)
        blocked_hostnames, blocked_terms = benchmark_decontam(benchmark_id)
        await run_eval_suite(
            dataset_id=benchmark_id,
            reports_dir=reports_dir,
            profile_id=profile_id,
            benchmark_mode=benchmark_mode,
            benchmark_tools=benchmark_required_tools(benchmark_id),
            external_cases=cases,
            workspace_seed_map=seed_map,
            limit=sample_size,
            max_tool_calls=max_tool_calls,
            max_iterations=max_iterations,
            blocked_hostnames=blocked_hostnames,
            blocked_terms=blocked_terms,
        )
    except Exception as exc:
        if _eval_state.get("abort_requested"):
            logger.info("Benchmark %s aborted by user", benchmark_id)
        else:
            logger.exception("Benchmark %s evaluation failed", benchmark_id)
            _eval_state["error"] = str(exc)
    finally:
        _reset_benchmark_state()


async def run_benchmark_download_background(
    benchmark_id: str,
    *,
    stage_label: str | None = None,
) -> None:
    """Download a benchmark in the background (download-only flow).

    Reuses the same global eval state and SSE stream as a full run so the UI
    can show live download progress; no evaluation is scheduled.
    """
    global _eval_state

    if not _eval_state.get("is_running"):
        _init_benchmark_state(stage_label or benchmark_id)

    try:
        from app.core.eval.benchmarks import ensure_benchmark_source

        # ensure_benchmark_source is sync (spawns its own event loop for the
        # download), so it must run off the calling loop — same pattern as the
        # full run flow below.
        await asyncio.to_thread(
            ensure_benchmark_source,
            benchmark_id,
            progress_callback=_report_benchmark_download_progress,
            should_abort=_benchmark_abort_requested,
        )
    except Exception as exc:
        if _eval_state.get("abort_requested"):
            logger.info("Benchmark %s download aborted by user", benchmark_id)
        else:
            logger.exception("Benchmark %s download failed", benchmark_id)
            _eval_state["error"] = str(exc)
    finally:
        _reset_benchmark_state()


async def run_wb_bench_background(
    subset_id: str,
    reports_dir: Path | None = None,
    profile_id: str | None = None,
    *,
    benchmark_mode: bool = False,
    limit: int | None = None,
) -> None:
    """Run a WorkBuddy Bench subset in the background (legacy-compatible handle).

    Delegates to the generic benchmark flow with the WBBench benchmark id.
    """
    await run_benchmark_background(
        f"wb-bench-{subset_id}",
        reports_dir=reports_dir,
        profile_id=profile_id,
        benchmark_mode=benchmark_mode,
        stage_label=subset_id,
        limit=limit,
    )


async def run_wb_bench_download_background(subset_id: str) -> None:
    """Download a WorkBuddy Bench subset in the background (legacy-compatible handle).

    Delegates to the generic benchmark download flow.
    """
    await run_benchmark_download_background(
        f"wb-bench-{subset_id}",
        stage_label=subset_id,
    )


async def run_eval_suite(
    dataset_id: str | None = None,
    reports_dir: Path | None = None,
    profile_id: str | None = None,
    *,
    benchmark_mode: bool = False,
    benchmark_tools: tuple[str, ...] = (),
    external_cases: list["MultiTurnEvalCase"] | None = None,
    workspace_seed_map: dict[str, str] | None = None,
    limit: int | None = None,
    max_tool_calls: int | None = None,
    max_iterations: int | None = None,
    blocked_hostnames: tuple[str, ...] = (),
    blocked_terms: tuple[str, ...] = (),
) -> dict[str, object]:
    """Run the standard evaluation suite for a user.

    Args:
        dataset_id: ID of the dataset to evaluate against.
        reports_dir: Directory where the evaluation report should be saved.
        profile_id: Optional ID of a specific Agent Profile to evaluate.
        benchmark_mode: When True, strips all user-specific configuration
            to produce a clean, fair baseline for harness-level benchmarks.
        benchmark_tools: Builtin-tool whitelist a benchmark declares for
            ``benchmark_mode`` (e.g. ``("web_search",)`` for BrowseComp),
            mounted on top of the CORE file/shell baseline.
        external_cases: Optional pre-built cases (e.g. WorkBuddy Bench) that
            bypass the JSONL dataset loading step.
        workspace_seed_map: Maps a case message to a pre-provisioned workspace
            directory that is copied into the session workspace before the
            agent runs (used by external dataset adapters).
        limit: Effective sample size already applied to ``external_cases``
            (recorded in the manifest so reports disclose sampled runs).
        max_tool_calls: Benchmark-declared tool-call budget to enforce during
            the run (None = engine default). Also recorded in the manifest.
        max_iterations: Benchmark-declared turn budget to enforce during
            the run (None = engine default). Also recorded in the manifest.
        blocked_hostnames: Hostname blocklist for benchmark decontamination,
            injected into web_fetch (empty = no filtering).
        blocked_terms: Search-query blocklist for benchmark decontamination,
            injected into web_search (empty = no filtering).

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
        benchmark_tools=benchmark_tools,
        workspace_seed_map=workspace_seed_map,
        max_tool_calls=max_tool_calls,
        max_iterations=max_iterations,
        blocked_hostnames=blocked_hostnames,
        blocked_terms=blocked_terms,
    )
    judge_config, judge_model_label = await _resolve_judge_config()
    adaptive_manager = AdaptiveEvalManager(max_concurrency=3, idle_wait_seconds=3.0)
    runner = EvalRunner(
        executor,
        max_concurrency=3,
        on_case_complete=_on_case_complete,
        yielding_strategy=adaptive_manager,
        judge_config=judge_config,
    )

    manifest = await _build_eval_manifest(
        profile_id=profile_id,
        dataset_id=dataset_id or "default",
        cases_path=cases_path,
        benchmark_mode=benchmark_mode,
        external_cases=external_cases,
        judge_model=judge_model_label,
        limit=limit,
        max_tool_calls=max_tool_calls,
        max_iterations=max_iterations,
    )

    logger.info(
        "Starting evaluation suite with %d sessions (%d turns) (Adaptive Yielding Enabled)",
        len(cases),
        total_turns,
    )
    _active_runner = runner
    try:
        result = await runner.run_multi_turn(cases, manifest=manifest)
    finally:
        _active_runner = None
        # Remove per-case session workspaces so eval never leaves throwaway
        # directories behind (success, error, or abort all land here).  A
        # cleanup failure must not mask the run's own outcome.
        try:
            await executor.cleanup()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to clean eval workspaces: %s", exc)

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
        "decontam_active": bool(blocked_hostnames or blocked_terms),
        "manifest": manifest.to_dict(),
        **({"avg_pass_rate": result.avg_pass_rate} if result.avg_pass_rate is not None else {}),
    }
