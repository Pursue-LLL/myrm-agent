"""Turn prewarm shared types.

[INPUT] (none — leaf type definitions)

[OUTPUT]
- TurnPrewarmJoinResult: prewarm join 结果 DTO

[POS]
execution_cache prewarm 类型层。定义 turn prewarm 共享 DTO。
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
