"""WorkBuddy Bench workspace provisioning and case building.

[INPUT]
- wb_bench.download::WbBenchSubset, _SUBSET_BY_ID, _safe_extract, WORKSPACES_DIR, _scoring_mode_for
- wb_bench.verifier::_test_suite_assertion_for
- myrm_agent_harness.eval::MultiTurnEvalCase, EvalCase, SandboxAssertion

[OUTPUT]
- build_wb_bench_cases(): map a subset's tasks to MultiTurnEvalCase + seed map
- _prepare_workspace(): extract task workspace.tar.gz into the workspace cache

[POS]
Splits task-level concerns (workspace seeding, case mapping) out of the
download/verify data-source management in ``wb_bench.download``; grading-command
wiring lives in ``wb_bench.verifier``. Seeded workspaces contain only the task
skeleton — grading assets are mounted read-only from the source cache at grading
time, so ``gold.patch`` never reaches the agent.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from collections.abc import Callable
from pathlib import Path

from myrm_agent_harness.eval import EvalCase, MultiTurnEvalCase, SandboxAssertion

from .download import (
    _SUBSET_BY_ID,
    WORKSPACES_DIR,
    DownloadAbortedError,
    WbBenchSubset,
    _safe_extract,
    _scoring_mode_for,
)
from .verifier import _test_suite_assertion_for

logger = logging.getLogger(__name__)


def _iter_task_dirs(source_root: Path) -> list[Path]:
    """Return task directories (each containing task.toml) under a source root."""
    tasks_root = source_root / "tasks"
    if not tasks_root.is_dir():
        return []
    return sorted(child for child in tasks_root.iterdir() if child.is_dir() and (child / "task.toml").exists())


def _read_instruction(task_dir: Path) -> str:
    """Read instruction.md, falling back to a generic prompt when absent."""
    instruction_path = task_dir / "instruction.md"
    if instruction_path.exists():
        return instruction_path.read_text(encoding="utf-8")
    return f"Complete the task described in the {task_dir.name} WorkBuddy Bench task."


def _single_root_dir(stage: Path) -> Path:
    """Return the effective content root, unwrapping a single top-level directory.

    Task workspace archives from Harbor often bundle the workspace under a
    named top-level directory (e.g. ``workspace/``). When the staging dir
    contains exactly one directory and no loose files, that directory is the
    content root; otherwise the staging dir itself is.
    """
    entries = list(stage.iterdir())
    subdirs = [entry for entry in entries if entry.is_dir()]
    if len(subdirs) == 1 and len(entries) == 1:
        return subdirs[0]
    return stage


def _prepare_workspace(task_dir: Path, subset: WbBenchSubset) -> Path | None:
    """Extract a task's workspace.tar.gz into the WBBench workspace cache.

    Returns the seeded workspace directory, or None when the task ships no
    workspace archive (in which case the agent starts from an empty sandbox).
    The extracted content lives in ``<cache>/workspace/`` and a ``.ready``
    marker at the cache root marks the extraction as complete so repeat runs
    are cheap and idempotent.

    Grading assets (``tests/``) intentionally stay out of the seeded workspace:
    they are mounted read-only from the source cache by the injected
    ``test_suite`` assertion (see ``wb_bench.verifier``), keeping ``gold.patch``
    unreachable during agent execution.
    """
    workspace_archive = task_dir / "environment" / "workspace.tar.gz"
    if not workspace_archive.is_file():
        return None

    cache_dir = WORKSPACES_DIR / subset.id / task_dir.name
    marker = cache_dir / ".ready"
    workspace_dir = cache_dir / "workspace"
    if marker.is_file() and workspace_dir.is_dir():
        return workspace_dir

    cache_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = cache_dir.parent / f".stage-{task_dir.name}"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    try:
        _safe_extract(workspace_archive, stage)
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
        workspace_dir.mkdir(parents=True)
        content_root = _single_root_dir(stage)
        for entry in content_root.iterdir():
            shutil.move(str(entry), workspace_dir)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    marker.touch()
    return workspace_dir


def _case_for_task(
    task_dir: Path,
    subset: WbBenchSubset,
    *,
    workspace_dir: Path | None,
) -> MultiTurnEvalCase:
    message = _read_instruction(task_dir)

    metadata: dict[str, str] = {
        "wb_bench_source": subset.id,
        "wb_bench_task_id": task_dir.name,
        "wb_bench_scoring": _scoring_mode_for(subset),
    }
    if workspace_dir:
        metadata["wb_bench_workspace"] = str(workspace_dir)

    # Web tasks grade through the VLM judge pipeline; any non-Web task that
    # ships a native verifier (Code/Security families, an Office task carrying
    # an Office verifier.toml, or a Security-style scoring.py) gets a Rule
    # assertion running its own grading command against the seeded workspace
    # (agent execution finished, so grading assets mounted read-only are never
    # reachable by the agent). Tasks without any verifier assets fall back to
    # the VLM/LLM judge pipeline via metadata only.
    sandbox_assertions: list[SandboxAssertion] = []
    if subset.id != "web" and workspace_dir is not None:
        assertion = _test_suite_assertion_for(task_dir)
        if assertion is not None:
            sandbox_assertions.append(assertion)

    return MultiTurnEvalCase(
        turns=[
            EvalCase(
                message=message,
                sandbox_assertions=sandbox_assertions,
                metadata=metadata,
            )
        ],
        metadata=metadata,
    )


def build_wb_bench_cases(
    subset_id: str,
    *,
    progress_callback: Callable[[int, int], None] | None = None,
    should_abort: Callable[[], bool] | None = None,
) -> tuple[list[MultiTurnEvalCase], dict[str, str]]:
    """Build runnable cases for a WBBench subset.

    Downloads the subset if missing, extracts each task's workspace archive,
    and returns ``(cases, workspace_seed_map)`` where the seed map keys are the
    case messages (consumed by LocalEvalExecutor.workspace_seed_map).
    ``progress_callback`` is forwarded to the download phase and ``should_abort``
    is honored both during the download stream and between task workspace
    preparations so a cancel surfaces promptly even on the first run.
    """
    from .download import ensure_wb_bench_source

    subset = _SUBSET_BY_ID.get(subset_id)
    if not subset:
        raise ValueError(f"Unknown WBBench subset: {subset_id}")

    source_root = asyncio.run(
        ensure_wb_bench_source(
            subset_id,
            progress_callback=progress_callback,
            should_abort=should_abort,
        )
    )
    task_dirs = _iter_task_dirs(source_root)

    cases: list[MultiTurnEvalCase] = []
    seed_map: dict[str, str] = {}
    for task_dir in task_dirs:
        if should_abort and should_abort():
            raise DownloadAbortedError(f"Workspace preparation for {subset_id} aborted")
        workspace_dir = _prepare_workspace(task_dir, subset)
        case = _case_for_task(task_dir, subset, workspace_dir=workspace_dir)
        cases.append(case)
        if workspace_dir:
            seed_map[case.turns[0].message] = str(workspace_dir)

    if not cases:
        raise ValueError(f"No runnable tasks found for WBBench subset {subset_id}")

    logger.info(
        "Built %d WBBench %s cases (%d with seeded workspaces)",
        len(cases),
        subset_id,
        len(seed_map),
    )
    return cases, seed_map
