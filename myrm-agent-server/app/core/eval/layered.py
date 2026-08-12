"""Layered evaluation — harness-config increment (ablation) comparisons.

[INPUT]
- myrm_agent_harness.eval::MatrixRunner
- app.core.eval.matrix::shared matrix state, eval_state.DEFAULT_MATRIX_REPORTS_DIR
- app.core.eval.benchmarks::build_benchmark_cases
- app.core.eval.model_config::model/judge resolution

[OUTPUT]
- run_layer_eval_background: background layered run.
- layer_specs_to_meta: layer chain disclosure with fingerprints.

[POS]
Reuses the matrix state machine, report directory and abort control so the
feature stays a first-class matrix variant on the Eval Lab UI.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.eval import AgentExecutor

from app.core.eval import _state as eval_state
from app.core.eval.adaptive import AdaptiveEvalManager
from app.core.eval.executor import LocalEvalExecutor

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

DEFAULT_LAYERS_MEMORY_DIR = eval_state.DEFAULT_MATRIX_REPORTS_DIR.parent / "eval_layers_memory"


@dataclass(frozen=True)
class LayerSpec:
    """One harness-configuration increment in the layered evaluation chain.

    Layers ascend from the bare benchmark baseline to the full agent
    configuration; the delta between adjacent layers isolates the capability
    switched on at that step (core rules, then skills, then memory).
    ``fingerprint`` pins the exact switch combination so a report stays
    comparable across harness versions (measurement-decay guard).
    """

    key: str
    benchmark_mode: bool
    skills_enabled: bool
    memory_enabled: bool

    def fingerprint(self) -> str:
        import hashlib

        payload = json.dumps(
            {
                "key": self.key,
                "benchmark_mode": self.benchmark_mode,
                "skills_enabled": self.skills_enabled,
                "memory_enabled": self.memory_enabled,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


# Ascending chain from the bare benchmark baseline to the full configuration.
# The final "memory" layer runs the profile in its normal (non-benchmark)
# mode — memory on, profile skills loaded — so it is the "full" comparison
# point; a separate full layer would be identical and is therefore omitted.
DEFAULT_LAYER_SPECS: tuple[LayerSpec, ...] = (
    LayerSpec("bare", benchmark_mode=True, skills_enabled=False, memory_enabled=False),
    LayerSpec("core", benchmark_mode=False, skills_enabled=False, memory_enabled=False),
    LayerSpec("skills", benchmark_mode=False, skills_enabled=True, memory_enabled=False),
    LayerSpec("memory", benchmark_mode=False, skills_enabled=True, memory_enabled=True),
)


def layer_specs_to_meta() -> list[dict[str, object]]:
    """Serialize the layer chain with fingerprints for report disclosure."""
    return [
        {
            "key": spec.key,
            "benchmark_mode": spec.benchmark_mode,
            "skills_enabled": spec.skills_enabled,
            "memory_enabled": spec.memory_enabled,
            "fingerprint": spec.fingerprint(),
        }
        for spec in DEFAULT_LAYER_SPECS
    ]


async def run_layer_eval_background(
    benchmark_id: str,
    profile_id: str | None = None,
    *,
    limit: int | None = None,
) -> None:
    """Run a layered (config-increment) evaluation on an external benchmark.

    The same dataset runs across the ascending layer chain, each layer a
    ``LocalEvalExecutor`` that differs only in the capability switches pinned
    by its ``LayerSpec``. The report carries the layer definitions and
    fingerprints, so the pass-rate delta between adjacent layers stays
    interpretable and comparable across harness versions. Reuses the matrix
    state machine and report directory, so the Eval Lab matrix tab streams
    progress and shows the report unchanged.
    """

    if eval_state.matrix_state.get("is_running"):
        return

    eval_state.matrix_state.update(
        {
            "is_running": True,
            "current_profile": None,
            "profile_progress": 0,
            "profile_total": len(DEFAULT_LAYER_SPECS),
            "case_completed": 0,
            "case_total": 0,
            "error": None,
            "abort_requested": False,
        }
    )

    try:
        await _run_layer_eval(benchmark_id, profile_id, limit=limit)
    except Exception as exc:
        logger.exception("Layered evaluation failed")
        eval_state.matrix_state["error"] = str(exc)
    finally:
        eval_state.matrix_state["is_running"] = False
        eval_state.active_matrix_runner = None


async def _run_layer_eval(
    benchmark_id: str,
    profile_id: str | None,
    *,
    limit: int | None = None,
) -> dict[str, object]:
    """Execute the layered evaluation suite against one profile."""

    from myrm_agent_harness.eval import MatrixRunner

    from app.core.eval.benchmarks import (
        benchmark_needs_judge,
        benchmark_required_tools,
        build_benchmark_cases,
    )
    from app.core.eval.model_config import (
        _resolve_agent_model_label,
        _resolve_judge_config,
    )

    def _report_download_progress(downloaded: int, total: int) -> None:
        eval_state.matrix_state["case_completed"] = downloaded
        eval_state.matrix_state["case_total"] = total

    def _should_abort() -> bool:
        return bool(eval_state.matrix_state.get("abort_requested"))

    cases, seed_map, sampled = await asyncio.to_thread(
        build_benchmark_cases,
        benchmark_id,
        limit=limit,
        progress_callback=_report_download_progress,
        should_abort=_should_abort,
    )
    if eval_state.matrix_state.get("abort_requested"):
        logger.info("Layered evaluation aborted by user before evaluation")
        return {}

    total_turns = sum(len(mc.turns) for mc in cases)
    eval_state.matrix_state["case_total"] = total_turns * len(DEFAULT_LAYER_SPECS)
    eval_state.matrix_state["case_completed"] = 0

    agent_model = await _resolve_agent_model_label(profile_id)

    judge_config = None
    judge_model = "none"
    if benchmark_needs_judge(benchmark_id):
        judge_config, judge_model = await _resolve_judge_config()

    benchmark_tools = benchmark_required_tools(benchmark_id)
    memory_dir = Path(DEFAULT_LAYERS_MEMORY_DIR) / f"layers_{int(time.time())}"

    executors: dict[str, AgentExecutor] = {}
    for spec in DEFAULT_LAYER_SPECS:
        executors[spec.key] = LocalEvalExecutor(
            profile_id=profile_id,
            benchmark_mode=spec.benchmark_mode,
            benchmark_tools=benchmark_tools,
            enable_memory=spec.memory_enabled,
            memory_base_path=str(memory_dir) if spec.memory_enabled else None,
            skill_ids_override=None if spec.skills_enabled else [],
            workspace_seed_map=seed_map,
        )

    def _on_layer_start(layer_key: str, idx: int, total: int) -> None:
        eval_state.matrix_state["current_profile"] = layer_key
        eval_state.matrix_state["profile_progress"] = idx

    def _on_case_complete(layer_key: str, result: object) -> None:
        cur = eval_state.matrix_state.get("case_completed")
        prev = int(cur) if isinstance(cur, int) else 0
        eval_state.matrix_state["case_completed"] = prev + 1

    adaptive_manager = AdaptiveEvalManager(max_concurrency=3, idle_wait_seconds=3.0)
    runner = MatrixRunner(
        executors,
        max_concurrency_per_profile=3,
        on_profile_start=_on_layer_start,
        on_case_complete=_on_case_complete,
        yielding_strategy=adaptive_manager,
        judge_config=judge_config,
    )
    eval_state.active_matrix_runner = runner

    try:
        matrix_result = await runner.run_multi_turn(cases)
    finally:
        eval_state.active_matrix_runner = None
        # Release the throwaway memory volume (SQLite + embedded Qdrant) from
        # the manager cache so the directory can be removed cleanly.
        from app.core.memory.adapters.setup import evict_cached_memory_manager

        try:
            await evict_cached_memory_manager(memory_dir)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to evict layered-eval memory cache: %s", exc)
        shutil.rmtree(memory_dir, ignore_errors=True)
        # Remove per-case session workspaces so the run never leaves
        # throwaway directories behind (success, error, or abort).
        for eval_executor in executors.values():
            try:
                await eval_executor.cleanup()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to clean layered-eval workspaces: %s", exc)

    eval_state.matrix_state["profile_progress"] = len(DEFAULT_LAYER_SPECS)

    reports_dir = eval_state.DEFAULT_MATRIX_REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)

    timestamp = int(time.time())
    report_path = reports_dir / f"matrix_report_{timestamp}.json"

    report_data = matrix_result.to_dict()
    report_data["timestamp"] = timestamp
    report_data["dataset_id"] = benchmark_id
    report_data["profile_id"] = profile_id
    # Disclose which model was scored and which model judged it, matching the
    # Memory A/B / benchmark-manifest disclosure so scores stay traceable
    # after the user switches models.
    report_data["judge_model"] = judge_model
    report_data["agent_model"] = agent_model
    report_data["limit"] = limit if sampled else None
    # Layer chain with fingerprints — the delta between adjacent per-layer
    # pass rates is what the UI renders, and the fingerprint pins the exact
    # switch combination for cross-version comparability.
    report_data["layers"] = layer_specs_to_meta()

    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    latest_path = reports_dir / "latest.json"
    if latest_path.exists():
        latest_path.unlink()
    shutil.copy2(report_path, latest_path)

    logger.info("Layered evaluation completed. Report: %s", report_path)
    return report_data
