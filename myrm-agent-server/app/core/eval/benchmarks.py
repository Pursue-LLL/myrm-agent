"""External benchmark catalog — unified list / run / download entry for the Eval Lab.

[INPUT]
- myrm_agent_harness.eval::list_benchmarks, get_benchmark (POS: framework registry)
- app.core.eval.wb_bench::list_wb_bench_sources, build_wb_bench_cases,
  ensure_wb_bench_source (POS: WorkBuddy Bench adapter)
- app.core.eval.browse_comp::list_browse_comp_source, build_browse_comp_cases,
  ensure_browse_comp_source (POS: BrowseComp adapter)

[OUTPUT]
- list_benchmark_sources(): merged catalog (WBBench + registered third-party)
- ensure_benchmark_source(): download-only dispatch
- build_benchmark_cases(): case-building dispatch (returns cases + seed map)

[POS]
Business-layer facade that merges the WorkBuddy Bench dedicated adapter with
any benchmark registered in the framework registry (e.g. BrowseComp) into one
catalog the eval service and the frontend consume. Dispatch keys on the
``wb-bench-`` prefix for the dedicated adapter; everything else resolves
through the registry + the ``build_cases`` adapter contract.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path

from myrm_agent_harness.eval import MultiTurnEvalCase, get_benchmark, list_benchmarks

logger = logging.getLogger(__name__)

WB_BENCH_PREFIX = "wb-bench-"


def list_benchmark_sources() -> list[dict[str, object]]:
    """Return the merged benchmark catalog with local availability flags.

    WorkBuddy Bench subsets carry their existing catalog fields (with the
    ``benchmark_id`` = ``wb-bench-<subset>`` handle the run/download APIs
    consume); every framework-registered third-party benchmark (e.g.
    BrowseComp) is appended with its own ``benchmark_id``.
    """
    from app.core.eval.browse_comp import list_browse_comp_source
    from app.core.eval.wb_bench import list_wb_bench_sources

    sources: list[dict[str, object]] = []
    for source in list_wb_bench_sources():
        subset_id = str(source["id"])
        sources.append(
            {
                **source,
                "benchmark_id": f"{WB_BENCH_PREFIX}{subset_id}",
                "provider": "wb_bench",
                "supports_memory_ab": True,
                "required_tools": [],
            }
        )
    for spec in list_benchmarks():
        source = spec.to_dict()
        if spec.id == "browsecomp":
            source = {**source, **list_browse_comp_source()}
        sources.append(
            {
                **source,
                "benchmark_id": spec.id,
                "provider": "external",
                "supports_memory_ab": spec.supports_memory_ab,
            }
        )
    return sources


def _known_benchmark_ids() -> frozenset[str]:
    """All benchmark handles the run/download APIs accept."""
    return frozenset(
        [f"{WB_BENCH_PREFIX}{s['id']}" for s in _wb_bench_subset_catalog()]
        + [spec.id for spec in list_benchmarks()]
    )


def _wb_bench_subset_catalog() -> list[dict[str, object]]:
    from app.core.eval.wb_bench import list_wb_bench_sources

    return list_wb_bench_sources()


def is_known_benchmark(benchmark_id: str) -> bool:
    """Return whether a benchmark id is runnable by the eval service."""
    return benchmark_id in _known_benchmark_ids()


def ensure_benchmark_source(
    benchmark_id: str,
    *,
    progress_callback: Callable[[int, int], None] | None = None,
    should_abort: Callable[[], bool] | None = None,
) -> Path:
    """Download-only dispatch for a benchmark handle (offline-friendly).

    Returns the extracted source root the run flow later consumes.
    """
    from app.core.eval.browse_comp import ensure_browse_comp_source
    from app.core.eval.wb_bench import ensure_wb_bench_source

    if benchmark_id.startswith(WB_BENCH_PREFIX):
        subset_id = benchmark_id.removeprefix(WB_BENCH_PREFIX)
        return asyncio.run(
            ensure_wb_bench_source(
                subset_id,
                progress_callback=progress_callback,
                should_abort=should_abort,
            )
        )
    if benchmark_id == "browsecomp":
        return asyncio.run(
            ensure_browse_comp_source(
                progress_callback=progress_callback,
                should_abort=should_abort,
            )
        )
    raise ValueError(f"Unknown benchmark: {benchmark_id}")


def build_benchmark_cases(
    benchmark_id: str,
    *,
    limit: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    should_abort: Callable[[], bool] | None = None,
) -> tuple[list[MultiTurnEvalCase], dict[str, str]]:
    """Build runnable cases + workspace seed map for a benchmark handle.

    ``limit`` caps the number of cases (random uniform sample with a fixed
    seed, so repeated runs with the same limit are reproducible — aligned with
    simple-evals' ``num_examples``). Sampling applies to every benchmark type,
    which lets users validate a small slice before paying for a full run.

    Returns ``(cases, workspace_seed_map)``; the seed map is empty for
    benchmarks without a pre-provisioned task workspace (e.g. BrowseComp).
    """
    import random

    from app.core.eval.browse_comp import build_browse_comp_cases
    from app.core.eval.wb_bench import build_wb_bench_cases

    if benchmark_id.startswith(WB_BENCH_PREFIX):
        subset_id = benchmark_id.removeprefix(WB_BENCH_PREFIX)
        cases, seed_map = build_wb_bench_cases(
            subset_id,
            progress_callback=progress_callback,
            should_abort=should_abort,
        )
    elif benchmark_id == "browsecomp":
        cases, seed_map = build_browse_comp_cases(
            progress_callback=progress_callback,
            should_abort=should_abort,
        )
    else:
        raise ValueError(f"Unknown benchmark: {benchmark_id}")

    if limit is not None and limit > 0 and len(cases) > limit:
        rng = random.Random(42)
        sampled = rng.sample(list(range(len(cases))), limit)
        kept = [cases[i] for i in sampled]
        kept_messages = {c.turns[0].message for c in kept}
        seed_map = {msg: seed_map[msg] for msg in kept_messages if msg in seed_map}
        cases = kept
    return cases, seed_map


def benchmark_required_tools(benchmark_id: str) -> tuple[str, ...]:
    """Return the builtin-tool whitelist a benchmark declares for benchmark_mode."""
    if benchmark_id.startswith(WB_BENCH_PREFIX):
        return ()
    spec = get_benchmark(benchmark_id)
    return spec.required_tools if spec else ()


def benchmark_needs_judge(benchmark_id: str) -> bool:
    """Return whether a benchmark is graded by an LLM judge.

    WorkBuddy Bench subsets are scored by task-native test suites (no judge
    LLM); registered third-party benchmarks declare their scoring strategy on
    the spec (BrowseComp uses ``llm_judge``).
    """
    if benchmark_id.startswith(WB_BENCH_PREFIX):
        return False
    spec = get_benchmark(benchmark_id)
    return spec.scoring == "llm_judge" if spec else False
