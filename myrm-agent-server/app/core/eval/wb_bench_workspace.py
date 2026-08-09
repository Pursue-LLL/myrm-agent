"""WorkBuddy Bench workspace provisioning and case building.

[INPUT]
- wb_bench::WbBenchSubset, _SUBSET_BY_ID, _safe_extract, WORKSPACES_DIR,
  _NATIVE_SCORING_SUBSETS, _COMPOSITE_SCORING_SUBSETS, _scoring_mode_for
- myrm_agent_harness.eval::MultiTurnEvalCase, EvalCase, SandboxAssertion

[OUTPUT]
- build_wb_bench_cases(): map a subset's tasks to MultiTurnEvalCase + seed map
- _prepare_workspace(): extract task workspace.tar.gz into the workspace cache
- _test_suite_assertion_for(): Rule judge assertion for a subset's tests

[POS]
Splits task-level concerns (workspace seeding, test mirroring, case mapping)
out of the download/verify data-source management in ``wb_bench``.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from collections.abc import Callable
from pathlib import Path

from myrm_agent_harness.eval import EvalCase, MultiTurnEvalCase, SandboxAssertion

from .wb_bench import (
    _NATIVE_SCORING_SUBSETS,
    _SUBSET_BY_ID,
    WORKSPACES_DIR,
    DownloadAbortedError,
    WbBenchSubset,
    _safe_extract,
    _scoring_mode_for,
)

logger = logging.getLogger(__name__)


def _iter_task_dirs(source_root: Path) -> list[Path]:
    """Return task directories (each containing task.toml) under a source root."""
    tasks_root = source_root / "tasks"
    if not tasks_root.is_dir():
        return []
    return sorted(
        child
        for child in tasks_root.iterdir()
        if child.is_dir() and (child / "task.toml").exists()
    )


def _read_instruction(task_dir: Path) -> str:
    """Read instruction.md, falling back to a generic prompt when absent."""
    instruction_path = task_dir / "instruction.md"
    if instruction_path.exists():
        return instruction_path.read_text(encoding="utf-8")
    return f"Complete the task described in the {task_dir.name} WorkBuddy Bench task."


def _test_suite_assertion_for(subset: WbBenchSubset) -> SandboxAssertion:
    """Build the Rule judge assertion that grades a task's own test suite.

    Code/Office tasks ship a pytest suite under ``tests/``; the assertion runs
    pytest with a JUnit XML report and the harness parses pass/total from it.
    Security tasks ship a native scorer driven by ``tests/test.sh`` that writes
    a numeric ``reward.json``; the assertion runs that script and the harness
    parses the reward. ``.wb_bench/tests`` is the mirrored copy the adapter
    places inside the seeded workspace (see ``_mirror_task_tests``). Commands
    default to a 600s timeout to match WBBench's ``[verifier] timeout_sec``.
    """
    timeout = 600
    if subset.id in _NATIVE_SCORING_SUBSETS:
        return SandboxAssertion(
            type="test_suite",
            target="bash .wb_bench/tests/test.sh",
            result_file=".wb_bench/reward.json",
            timeout=timeout,
        )
    return SandboxAssertion(
        type="test_suite",
        target="python -m pytest -q .wb_bench/tests --junitxml=.wb_bench/results.xml",
        result_file=".wb_bench/results.xml",
        timeout=timeout,
    )


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


def _mirror_task_tests(task_dir: Path, workspace_dir: Path) -> None:
    """Copy a task's grading tests into the workspace as ``.wb_bench/tests``.

    Idempotent: an existing mirror (from a previous run or a pre-built cache)
    is left untouched, so this is cheap on the hot path and never overwrites
    work an agent may have produced under that hidden directory.
    """
    tests_src = task_dir / "tests"
    if not tests_src.is_dir():
        return
    tests_dst = workspace_dir / ".wb_bench" / "tests"
    if tests_dst.exists():
        return
    tests_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(tests_src, tests_dst)


def _prepare_workspace(task_dir: Path, subset: WbBenchSubset) -> Path | None:
    """Extract a task's workspace.tar.gz into the WBBench workspace cache.

    Returns the seeded workspace directory, or None when the task ships no
    workspace archive (in which case the agent starts from an empty sandbox).
    The extracted content lives in ``<cache>/workspace/`` and a ``.ready``
    marker at the cache root marks the extraction as complete so repeat runs
    are cheap and idempotent.

    Task-owned grading assets (``tests/``) are mirrored into the workspace
    under ``.wb_bench/tests`` so the harness Rule judge can run them inside
    the same directory the agent worked in. The hidden dot-directory keeps the
    test suite out of the agent's working files while remaining reachable by
    the injected ``test_suite`` assertion command.
    """
    workspace_archive = task_dir / "environment" / "workspace.tar.gz"
    if not workspace_archive.is_file():
        return None

    cache_dir = WORKSPACES_DIR / subset.id / task_dir.name
    marker = cache_dir / ".ready"
    workspace_dir = cache_dir / "workspace"
    if marker.is_file() and workspace_dir.is_dir():
        _mirror_task_tests(task_dir, workspace_dir)
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
    _mirror_task_tests(task_dir, workspace_dir)
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

    # Web tasks grade through the VLM judge pipeline; Code/Office/Security
    # carry a rule assertion that runs the task's own tests inside the seeded
    # workspace (only when the task ships a workspace with mirrored tests).
    sandbox_assertions: list[SandboxAssertion] = []
    if (
        subset.id != "web"
        and workspace_dir is not None
        and (workspace_dir / ".wb_bench" / "tests").is_dir()
    ):
        sandbox_assertions.append(_test_suite_assertion_for(subset))

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
    from .wb_bench import ensure_wb_bench_source

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
