"""[INPUT]
- none (imports no other project module)

[OUTPUT]
- MentionContext: per-turn accumulation state shared by the pipeline and every reference handler
  (resolved workspace, agent id, emitted fragments, bytes consumed so far)

[POS]
The mutable state of one @-mention expansion. Handlers append fragments and add their byte cost;
the pipeline owns the budget policy that reads it, so no handler needs to know the limits.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class MentionContext:
    workspace_real: str
    agent_id: str | None = None
    parts: list[str] = field(default_factory=list)
    total_bytes: int = 0
    warnings: list[str] = field(default_factory=list)
