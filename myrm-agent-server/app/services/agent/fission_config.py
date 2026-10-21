"""Resolve swarm fission runtime limits from agent engine parameters.

[INPUT]
- myrm_agent_harness.agent.parallel.config::resolve_max_parallel_fission (POS: Parallel concurrency defaults and caps)

[OUTPUT]
- max_parallel_from_engine_params: Read max_parallel_fission from Agent engine_params

[POS]
Server-side helper for Swarm Fission concurrency. Keeps Web, Channel, Kanban, and FastSearch
aligned on the same max_parallel_fission contract stored in Agent engine_params.
"""

from __future__ import annotations

from myrm_agent_harness.agent.parallel.config import resolve_max_parallel_fission


def max_parallel_from_engine_params(
    engine_params: dict[str, object] | None,
) -> int:
    """Read ``max_parallel_fission`` from agent engine_params with safe defaults."""
    raw: int | None = None
    if engine_params is not None:
        value = engine_params.get("max_parallel_fission")
        if isinstance(value, bool):
            raw = None
        elif isinstance(value, int):
            raw = value
        elif isinstance(value, float):
            raw = int(value)
        elif isinstance(value, str) and value.isdigit():
            raw = int(value)
    return resolve_max_parallel_fission(raw)
