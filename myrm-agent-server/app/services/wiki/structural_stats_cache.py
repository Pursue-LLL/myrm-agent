"""TTL cache for deterministic wiki structural lint stats.

[INPUT]
myrm_agent_harness.toolkits.wiki.core.structure::WikiStructure (POS: wiki filesystem layout)
myrm_agent_harness.toolkits.wiki.diagnostics.structural_lint::collect_structural_lint_snapshot (POS: structural lint scan)

[OUTPUT]
get_structural_lint_snapshot_cached: cached StructuralLintSnapshot for /wiki/stats
invalidate_structural_lint_cache: drop TTL entry after vault mutations

[POS]
Server wiki service helper. Short-TTL cache for structural lint counts on /wiki/stats; invalidated by compile/maintain/repair-types/import routes and ingest tree-sync.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.toolkits.wiki.diagnostics.structural_lint import (
    StructuralLintSnapshot,
    collect_structural_lint_snapshot,
)

_STRUCTURAL_STATS_TTL_SECONDS = 120.0
_cache: dict[str, tuple[float, StructuralLintSnapshot]] = {}


@dataclass(frozen=True, slots=True)
class CachedStructuralLintSnapshot:
    """Structural lint counts served from cache or fresh scan."""

    snapshot: StructuralLintSnapshot
    cache_hit: bool


def get_structural_lint_snapshot_cached(
    structure: WikiStructure,
) -> CachedStructuralLintSnapshot:
    """Return structural lint counts with a short TTL to protect /wiki/stats latency."""
    cache_key = str(structure.base_dir.resolve())
    now = time.monotonic()
    cached = _cache.get(cache_key)
    if cached is not None and cached[0] > now:
        return CachedStructuralLintSnapshot(snapshot=cached[1], cache_hit=True)

    snapshot = collect_structural_lint_snapshot(structure)
    _cache[cache_key] = (now + _STRUCTURAL_STATS_TTL_SECONDS, snapshot)
    return CachedStructuralLintSnapshot(snapshot=snapshot, cache_hit=False)


def invalidate_structural_lint_cache(structure: WikiStructure) -> None:
    """Drop cached structural lint counts after vault mutations that affect concept files."""
    _cache.pop(str(structure.base_dir.resolve()), None)
