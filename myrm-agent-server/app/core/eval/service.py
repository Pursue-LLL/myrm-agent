"""Eval Service for the Server Layer.

[INPUT]
- myrm_agent_harness.eval::EvalRunner, EvalManifest, JsonlReporter
- app.core.eval.executor::LocalEvalExecutor
- app.core.eval.adaptive::AdaptiveEvalManager
- app.core.eval.datasets::get_dataset_path
- app.core.eval.reports::DEFAULT_REPORTS_DIR

[OUTPUT]
- run_eval_suite: runs the standard eval suite for a user.
- run_eval_suite_background: background wrapper with progress via _eval_state.
- run_wb_bench_background / run_wb_bench_download_background: WorkBuddy Bench
  subset run and download-only flows with progress via _eval_state.

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
    EvalManifest,
    EvalRunner,
    JsonlReporter,
)

from app.core.eval.adaptive import AdaptiveEvalManager
from app.core.eval.datasets import get_dataset_path
from app.core.eval.executor import LocalEvalExecutor
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
        from app.services.agent.profile.profile_resolver import get_agent_profile_resolver

        resolved = await get_agent_profile_resolver().resolve(profile_id)
        if resolved:
            if resolved.model:
                parts = resolved.model.split("/", 1)
                if len(parts) == 2:
                    model_provider, model_id = parts
                else:
                    model_id = resolved.model
            if resolved.engine_params:
                thinking_effort = str(
                    resolved.engine_params.get("thinking_effort", "default")
                )
                max_tokens_value = resolved.engine_params.get(
                    "max_tokens", budget_max_tokens
                )
                if isinstance(max_tokens_value, int):
                    budget_max_tokens = max_tokens_value
                elif isinstance(max_tokens_value, str) and max_tokens_value.isdigit():
                    budget_max_tokens = int(max_tokens_value)
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
        except (
            Exception
        ):  # noqa: BLE001 - fall back to a stable marker on any serialization edge case
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


async def run_benchmark_background(
    benchmark_id: str,
    reports_dir: Path | None = None,
    profile_id: str | None = None,
    *,
    benchmark_mode: bool = False,
    stage_label: str | None = None,
) -> None:
    """Run an external benchmark (WBBench subset or registered third-party).

    Resolves the benchmark through ``benchmarks`` (WBBench subsets or the
    framework registry), downloads if needed, builds runnable cases, and runs
    the eval suite with the benchmark's declared tool whitelist. ``stage_label``
    overrides the SSE ``stage_subset_id`` (WBBench keeps its bare subset id for
    existing frontend compatibility).
    """
    global _eval_state

    # The router marks is_running synchronously before scheduling this task so
    # the SSE stream opened on "started" never reads a stale idle first frame.
    # If the state was not pre-initialized (direct/legacy callers), do it here.
    if not _eval_state.get("is_running"):
        _init_benchmark_state(stage_label or benchmark_id)

    try:
        from app.core.eval.benchmarks import (
            build_benchmark_cases,
            benchmark_required_tools,
        )

        cases, seed_map = await asyncio.to_thread(
            build_benchmark_cases,
            benchmark_id,
            progress_callback=_report_wb_bench_download_progress,
            should_abort=_wb_bench_abort_requested,
        )
        # An abort during the download/extract worker phase is only visible
        # after the thread returns; never start evaluating after a cancel.
        if _eval_state.get("abort_requested"):
            logger.info("Benchmark %s aborted by user before evaluation", benchmark_id)
            return
        _eval_state["stage"] = "evaluating"
        await run_eval_suite(
            dataset_id=benchmark_id,
            reports_dir=reports_dir,
            profile_id=profile_id,
            benchmark_mode=benchmark_mode,
            benchmark_tools=benchmark_required_tools(benchmark_id),
            external_cases=cases,
            workspace_seed_map=seed_map,
        )
    except Exception as exc:
        if _eval_state.get("abort_requested"):
            logger.info("Benchmark %s aborted by user", benchmark_id)
        else:
            logger.exception("Benchmark %s evaluation failed", benchmark_id)
            _eval_state["error"] = str(exc)
    finally:
        _reset_wb_bench_state()


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

        await ensure_benchmark_source(
            benchmark_id,
            progress_callback=_report_wb_bench_download_progress,
            should_abort=_wb_bench_abort_requested,
        )
    except Exception as exc:
        if _eval_state.get("abort_requested"):
            logger.info("Benchmark %s download aborted by user", benchmark_id)
        else:
            logger.exception("Benchmark %s download failed", benchmark_id)
            _eval_state["error"] = str(exc)
    finally:
        _reset_wb_bench_state()


async def run_wb_bench_background(
    subset_id: str,
    reports_dir: Path | None = None,
    profile_id: str | None = None,
    *,
    benchmark_mode: bool = False,
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
                f.write(
                    '{"message": "What is 2+2?", "expected_tools": ["code_exec"]}\n'
                )

        from myrm_agent_harness.eval import load_multi_turn_cases

        cases = load_multi_turn_cases(cases_path)

        # Group cases by profile_id to maximize LLM Prompt Cache hits
        cases.sort(key=lambda c: str(c.metadata.get("profile_id", "default")))
        grouped_cases = []
        for _, group in groupby(
            cases, key=lambda c: str(c.metadata.get("profile_id", "default"))
        ):
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
    )
    adaptive_manager = AdaptiveEvalManager(max_concurrency=3, idle_wait_seconds=3.0)
    runner = EvalRunner(
        executor,
        max_concurrency=3,
        on_case_complete=_on_case_complete,
        yielding_strategy=adaptive_manager,
    )

    manifest = await _build_eval_manifest(
        profile_id=profile_id,
        dataset_id=dataset_id or "default",
        cases_path=cases_path,
        benchmark_mode=benchmark_mode,
        external_cases=external_cases,
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
        **(
            {"avg_pass_rate": result.avg_pass_rate}
            if result.avg_pass_rate is not None
            else {}
        ),
    }
