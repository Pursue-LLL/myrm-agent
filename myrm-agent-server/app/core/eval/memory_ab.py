"""Memory A/B Eval — memory-on vs memory-off comparative evaluation.

[INPUT]
- myrm_agent_harness.eval::MatrixRunner, AgentExecutor
- app.core.eval.reports::DEFAULT_REPORTS_DIR
- app.core.eval.adaptive::AdaptiveEvalManager
- app.core.memory.adapters.setup::evict_cached_memory_manager
- app.core.eval.model_config::_resolve_agent_model_label / _resolve_judge_config (POS: 统一模型解析与 judge 注入)

[OUTPUT]
- get_memory_ab_status / abort_memory_ab: progress query and abort.
- run_memory_ab_background: background memory-on vs memory-off run.
- get_latest_memory_ab_report / get_memory_ab_report / get_memory_ab_report_history.

[POS]
Reuses MatrixRunner (same cross-profile orchestration) with two executors
that share an identical benchmark environment and differ only in whether the
agent memory system is enabled. The memory-on arm writes to a throwaway
volume under `.myrm/eval_memory_ab/` that is evicted and removed after the
run, so evaluation can never read or pollute the user's real memories.
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
from myrm_agent_harness.eval import AgentExecutor

from app.core.eval.adaptive import AdaptiveEvalManager
from app.core.eval.executor import LocalEvalExecutor
from app.core.eval.reports import DEFAULT_REPORTS_DIR

if TYPE_CHECKING:
    from myrm_agent_harness.eval import MatrixRunner

logger = logging.getLogger(__name__)

_memory_ab_state: dict[str, object] = {
    "is_running": False,
    "stage": None,
    "stage_subset_id": None,
    "download_progress": {"downloaded_bytes": 0, "total_bytes": 0},
    "current_arm": None,
    "profile_progress": 0,
    "profile_total": 0,
    "case_completed": 0,
    "case_total": 0,
    "error": None,
    "abort_requested": False,
}

_active_memory_ab_runner: "MatrixRunner | None" = None

DEFAULT_MEMORY_AB_REPORTS_DIR = DEFAULT_REPORTS_DIR.parent / "memory_ab_reports"
DEFAULT_MEMORY_AB_MEMORY_DIR = DEFAULT_REPORTS_DIR.parent / "eval_memory_ab"


def _init_memory_ab_state(benchmark_id: str) -> None:
    """Reset global state for a memory A/B run (called synchronously by the router)."""
    _memory_ab_state.clear()
    _memory_ab_state.update(
        {
            "is_running": True,
            "stage": "downloading",
            "stage_subset_id": benchmark_id,
            "download_progress": {"downloaded_bytes": 0, "total_bytes": 0},
            "current_arm": None,
            "profile_progress": 0,
            "profile_total": 2,
            "case_completed": 0,
            "case_total": 0,
            "error": None,
            "abort_requested": False,
        }
    )


def _report_memory_ab_download_progress(downloaded: int, total: int) -> None:
    """Record the benchmark download progress into the memory A/B state."""
    _memory_ab_state["download_progress"] = {
        "downloaded_bytes": downloaded,
        "total_bytes": total,
    }


def _memory_ab_abort_requested() -> bool:
    """Report whether the user requested abort of the memory A/B run."""
    return bool(_memory_ab_state.get("abort_requested"))


def get_memory_ab_status() -> dict[str, object]:
    """Get current memory A/B evaluation status."""
    return dict(_memory_ab_state)


def abort_memory_ab() -> bool:
    """Request abort of the currently running memory A/B evaluation."""
    global _active_memory_ab_runner
    if not _memory_ab_state.get("is_running"):
        return False
    _memory_ab_state["abort_requested"] = True
    if _active_memory_ab_runner:
        _active_memory_ab_runner.abort()
    return True


async def run_memory_ab_background(
    benchmark_id: str,
    profile_id: str | None = None,
    *,
    limit: int | None = None,
) -> None:
    """Run a memory-on vs memory-off A/B comparison on an external benchmark.

    Both arms use ``benchmark_mode`` so they share a clean, user-config-free
    environment; the only difference is ``enable_memory``. The memory-on arm
    is pointed at a throwaway volume that is evicted from the memory manager
    cache and deleted when the run finishes. The benchmark's declared tool
    whitelist (e.g. ``web_search`` for BrowseComp) is injected into both arms.
    ``limit`` caps the case count for both arms (same sample, so the
    comparison stays fair) for low-cost validation runs.
    """
    global _memory_ab_state, _active_memory_ab_runner

    if not _memory_ab_state.get("is_running"):
        _init_memory_ab_state(benchmark_id)

    memory_dir = Path(DEFAULT_MEMORY_AB_MEMORY_DIR) / f"memory_ab_{int(time.time())}"
    executors: dict[str, AgentExecutor] = {}

    try:
        from app.core.eval.benchmarks import (
            benchmark_decontam,
            benchmark_needs_judge,
            benchmark_required_tools,
            benchmark_run_limits,
            build_benchmark_cases,
        )

        cases, seed_map, sampled = await asyncio.to_thread(
            build_benchmark_cases,
            benchmark_id,
            limit=limit,
            progress_callback=_report_memory_ab_download_progress,
            should_abort=_memory_ab_abort_requested,
        )
        if _memory_ab_state.get("abort_requested"):
            logger.info("Memory A/B aborted by user before evaluation")
            return
        _memory_ab_state["stage"] = "evaluating"

        total_turns = sum(len(mc.turns) for mc in cases)
        _memory_ab_state["case_total"] = total_turns * 2

        from myrm_agent_harness.eval import MatrixRunner

        # Disclose which agent model was evaluated, regardless of the scoring
        # mode, so a later score change caused by switching the user's model
        # stays traceable (same resolution as benchmark-report manifests).
        from app.core.eval.model_config import _resolve_agent_model_label

        agent_model = await _resolve_agent_model_label(profile_id)

        # Only LLM-judge benchmarks need the caller's judge credentials; for
        # native-scored suites (e.g. WorkBuddy Bench) the judge is never
        # invoked, so skip the config resolution entirely.
        judge_config = None
        judge_model = "none"
        if benchmark_needs_judge(benchmark_id):
            from app.core.eval.model_config import _resolve_judge_config

            judge_config, judge_model = await _resolve_judge_config()

        benchmark_tools = benchmark_required_tools(benchmark_id)
        max_tool_calls, max_iterations = benchmark_run_limits(benchmark_id)
        blocked_hostnames, blocked_terms = benchmark_decontam(benchmark_id)
        executors = {
            "memory_off": LocalEvalExecutor(
                profile_id=profile_id,
                benchmark_mode=True,
                benchmark_tools=benchmark_tools,
                enable_memory=False,
                workspace_seed_map=seed_map,
                max_tool_calls=max_tool_calls,
                max_iterations=max_iterations,
                blocked_hostnames=blocked_hostnames,
                blocked_terms=blocked_terms,
            ),
            "memory_on": LocalEvalExecutor(
                profile_id=profile_id,
                benchmark_mode=True,
                benchmark_tools=benchmark_tools,
                enable_memory=True,
                memory_base_path=str(memory_dir),
                workspace_seed_map=seed_map,
                max_tool_calls=max_tool_calls,
                max_iterations=max_iterations,
                blocked_hostnames=blocked_hostnames,
                blocked_terms=blocked_terms,
            ),
        }

        def _on_arm_start(arm_id: str, idx: int, total: int) -> None:
            _memory_ab_state["current_arm"] = arm_id
            _memory_ab_state["profile_progress"] = idx

        def _on_case_complete(arm_id: str, result: object) -> None:
            cur = _memory_ab_state.get("case_completed")
            prev = int(cur) if isinstance(cur, int) else 0
            _memory_ab_state["case_completed"] = prev + 1

        adaptive_manager = AdaptiveEvalManager(max_concurrency=3, idle_wait_seconds=3.0)
        runner = MatrixRunner(
            executors,
            max_concurrency_per_profile=3,
            on_profile_start=_on_arm_start,
            on_case_complete=_on_case_complete,
            yielding_strategy=adaptive_manager,
            judge_config=judge_config,
        )
        _active_memory_ab_runner = runner
        try:
            matrix_result = await runner.run_multi_turn(cases)
        finally:
            _active_memory_ab_runner = None

        _memory_ab_state["profile_progress"] = 2

        reports_dir = DEFAULT_MEMORY_AB_REPORTS_DIR
        reports_dir.mkdir(parents=True, exist_ok=True)

        timestamp = int(time.time())
        report_path = reports_dir / f"memory_ab_report_{timestamp}.json"

        report_data = matrix_result.to_dict()
        report_data["timestamp"] = timestamp
        report_data["dataset_id"] = benchmark_id
        report_data["profile_id"] = profile_id
        report_data["benchmark_mode"] = True
        # Disclose the harness version so scores stay comparable across
        # framework upgrades (same measurement-decay guard as matrix/layered).
        report_data["harness_version"] = harness_version
        # Disclose the judge model used for LLM-graded benchmarks so a later
        # score change caused by switching the user's model stays traceable;
        # native-scored suites never invoke a judge and stay "none".
        report_data["judge_model"] = judge_model
        # The evaluated agent's model, paired with the judge model above, so
        # the report stays self-contained regardless of later profile changes.
        report_data["agent_model"] = agent_model
        # A user abort mid-run leaves partial results: mark the report so it
        # is never mistaken for a complete run (same flag as matrix/layered).
        report_data["aborted"] = bool(_memory_ab_state.get("abort_requested"))
        # Disclose the sample size only when a sample was actually drawn
        # (limit < full case count); a limit at/above the full count is a
        # full run and must not be flagged as sampled.
        report_data["limit"] = limit if sampled else None
        # Disclose the benchmark-declared run budgets so a later engine-default
        # change stays traceable (same measurement-decay guard as layered).
        report_data["max_tool_calls"] = max_tool_calls
        report_data["max_iterations"] = max_iterations

        # Annotate each arm with how many times the agent actually invoked
        # memory tools. Identical pass rates mean different things when memory
        # was never called versus actively engaged — without this number the
        # A/B report cannot tell "memory didn't help" from "memory was unused".
        for arm_id, arm_result in matrix_result.per_profile_results.items():
            memory_calls = sum(
                1
                for turn in getattr(arm_result, "turn_results", ()) or ()
                for tool in getattr(turn.response, "tools_called", ()) or ()
                if str(tool.get("name") if isinstance(tool, dict) else tool).startswith(
                    "memory_"
                )
            )
            per_profile = report_data.get("per_profile")
            if not isinstance(per_profile, dict):
                continue
            profile_summary = per_profile.get(arm_id)
            if isinstance(profile_summary, dict):
                profile_summary["memory_tool_calls"] = memory_calls

        with report_path.open("w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        latest_path = reports_dir / "latest.json"
        if latest_path.exists():
            latest_path.unlink()
        shutil.copy2(report_path, latest_path)

        logger.info("Memory A/B evaluation completed. Report: %s", report_path)
    except Exception as exc:
        if _memory_ab_state.get("abort_requested"):
            logger.info("Memory A/B evaluation aborted by user")
        else:
            logger.exception("Memory A/B evaluation failed")
            _memory_ab_state["error"] = str(exc)
    finally:
        _memory_ab_state["is_running"] = False
        _memory_ab_state["stage"] = None
        _memory_ab_state["stage_subset_id"] = None
        _active_memory_ab_runner = None
        # Release the throwaway memory volume (SQLite + embedded Qdrant) from
        # the manager cache so the directory can be removed cleanly.  Each
        # teardown step is independently guarded so a failure in one cannot
        # skip the workspace cleanup that must always run.
        from app.core.memory.adapters.setup import evict_cached_memory_manager

        try:
            await evict_cached_memory_manager(memory_dir)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to evict cached memory manager: %s", exc)
        try:
            shutil.rmtree(memory_dir, ignore_errors=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to remove memory volume: %s", exc)
        # Also remove the per-case session workspaces both arms created.
        for eval_executor in executors.values():
            try:
                await eval_executor.cleanup()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to clean eval workspaces: %s", exc)


def get_latest_memory_ab_report() -> dict[str, object] | None:
    """Get the latest memory A/B evaluation report."""
    latest_path = DEFAULT_MEMORY_AB_REPORTS_DIR / "latest.json"
    if not latest_path.exists():
        return None
    try:
        with latest_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            logger.warning("Latest memory A/B report is not an object")
            return None
        return data
    except Exception as exc:
        logger.warning("Failed to read memory A/B report: %s", exc)
        return None


def get_memory_ab_report(timestamp: int) -> dict[str, object] | None:
    """Get a specific memory A/B report by its run timestamp."""
    report_path = DEFAULT_MEMORY_AB_REPORTS_DIR / f"memory_ab_report_{timestamp}.json"
    if not report_path.exists():
        return None
    try:
        with report_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            logger.warning("Memory A/B report %s is not an object", report_path)
            return None
        return data
    except Exception as exc:
        logger.warning("Failed to read memory A/B report %s: %s", report_path, exc)
        return None


def _report_sort_key(item: dict[str, object]) -> int:
    """Sort key for report summaries: run timestamp, missing treated as 0."""
    ts = item.get("timestamp")
    return ts if isinstance(ts, int) else 0


def get_memory_ab_report_history(
    reports_dir: Path | None = None,
) -> list[dict[str, object]]:
    """Get all memory A/B reports, newest first.

    Returns a lightweight summary per run (timestamp, dataset, arms) so the
    UI can show a history list without shipping the full per-case matrix.
    """
    reports_dir = reports_dir or DEFAULT_MEMORY_AB_REPORTS_DIR
    if not reports_dir.exists():
        return []

    summaries: list[dict[str, object]] = []
    for report_path in reports_dir.glob("memory_ab_report_*.json"):
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
                    "judge_model": data.get("judge_model"),
                    "agent_model": data.get("agent_model"),
                    "limit": data.get("limit"),
                    "aborted": data.get("aborted", False),
                    "per_profile": data.get("per_profile", {}),
                }
            )
        except Exception as exc:
            logger.warning("Failed to read memory A/B report %s: %s", report_path, exc)

    summaries.sort(key=_report_sort_key, reverse=True)
    return summaries
