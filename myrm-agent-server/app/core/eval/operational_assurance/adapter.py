"""Operational Assurance Adapter & Benchmark Registration.

[INPUT]
- myrm_agent_harness.eval::BenchmarkSpec, register_benchmark, MultiTurnEvalCase
- .fixtures::build_operational_assurance_cases, SEED_WORKSPACE_DIR

[OUTPUT]
- OPERATIONAL_ASSURANCE_SPEC: BenchmarkSpec registration
- list_operational_assurance_source(): catalog representation
- ensure_operational_assurance_source(): local seed provisioning
- build_operational_assurance_benchmark_cases(): returns (cases, seed_map)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from myrm_agent_harness.eval import (
    BenchmarkSpec,
    MultiTurnEvalCase,
    register_benchmark,
)

from app.core.eval.operational_assurance.fixtures import (
    SEED_WORKSPACE_DIR,
    build_operational_assurance_cases,
)

logger = logging.getLogger(__name__)

OPERATIONAL_ASSURANCE_TASK_COUNT = 6

OPERATIONAL_ASSURANCE_SPEC = BenchmarkSpec(
    id="operational-assurance",
    display_name="Operational Assurance Audit Suite",
    description="Enterprise operational resilience & failure recovery audit across 6 core fault domains.",
    download_url="",
    task_count=OPERATIONAL_ASSURANCE_TASK_COUNT,
    approx_size_mb=1,
    scoring="composite",
    required_tools=(),
    supports_memory_ab=True,
    supports_compaction_ab=True,
    max_tool_calls=40,
    max_iterations=50,
    harness="myrm",
    judge_prompt="",
)

register_benchmark(OPERATIONAL_ASSURANCE_SPEC)


def list_operational_assurance_source() -> dict[str, object]:
    """Return catalog entry for Operational Assurance Suite."""
    return {
        **OPERATIONAL_ASSURANCE_SPEC.to_dict(),
        "is_downloaded": True,
        "local_size_bytes": 1024 * 64,
    }


def ensure_operational_assurance_source(
    *,
    progress_callback: Callable[[int, int], None] | None = None,
    should_abort: Callable[[], bool] | None = None,
) -> Path:
    """Ensure operational assurance seeds exist locally."""
    SEED_WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    if progress_callback:
        progress_callback(100, 100)
    return SEED_WORKSPACE_DIR


def build_operational_assurance_benchmark_cases(
    *,
    progress_callback: Callable[[int, int], None] | None = None,
    should_abort: Callable[[], bool] | None = None,
) -> tuple[list[MultiTurnEvalCase], dict[str, str]]:
    """Build runnable cases + seed map for the Operational Assurance suite."""
    ensure_operational_assurance_source(
        progress_callback=progress_callback,
        should_abort=should_abort,
    )
    return build_operational_assurance_cases()
