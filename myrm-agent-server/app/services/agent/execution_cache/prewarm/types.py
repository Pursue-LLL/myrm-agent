"""Turn prewarm shared types.

[INPUT] (none — leaf type definitions)

[OUTPUT]
- TurnPrewarmJoinResult (POS: prewarm join result DTO)

[POSITION] app.services.agent.execution_cache.prewarm — shared DTOs for turn prewarm.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TurnPrewarmJoinResult:
    preview: dict[str, object] | None
    snapshot: dict[str, object] | None
    brief_status: dict[str, object]
    prewarm_hit: bool
    prewarm_ms: int | None
    still_warming: bool
