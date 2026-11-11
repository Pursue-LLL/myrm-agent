"""System and user prompts for cross-cycle pattern discovery.

[INPUT]
- memory.types::AnyMemory (POS: memory data models)

[OUTPUT]
- MAX_PROMPT_MEMORIES: How many of the newest memories the user prompt lists
- _SYSTEM_PROMPT: Base system instructions declaring the exact output JSON field names
- _build_discovery_prompt: Serializes memories, insights and claims into the user prompt

[POS]
Prompts for cross-cycle pattern discovery: a constant system prompt and a user-prompt builder
over recent memories, consolidation insights and claim-graph content.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.types import AnyMemory

# The prompt lists the newest memories up to this count; the chats a discovered pattern derives from are those of the
# memories listed, so the strategy reads the same bound.
MAX_PROMPT_MEMORIES = 100

_SYSTEM_PROMPT = """You are a behavioral pattern analyst. Given a user's accumulated memories, consolidation insights, and knowledge claims, identify cross-cycle behavioral patterns the user may not be aware of.

Focus on:
1. **Recurring work habits** — repeated actions, schedules, or routines visible across multiple sessions
2. **Knowledge evolution** — topics where the user's understanding has shifted over time
3. **Unresolved threads** — questions, concerns, or tasks that appear repeatedly without closure
4. **Preference drift** — changes in tool choices, frameworks, or approaches over time
5. **Blind spots** — important areas that appear in context but the user never directly addresses

## Rules
- Only report patterns supported by multiple memories (not single observations).
- Be specific: cite time ranges, frequencies, or concrete examples from the evidence.
- Mark durability: "emerging" (seen in recent 1-2 cycles), "established" (3+ cycles), "declining" (was active, now fading).
- Provide actionable suggestions where appropriate (the agent will present these proactively).
- Keep the original language of the memories (Chinese stays Chinese, English stays English).
- Maximum 5 patterns per analysis.
- Do NOT invent patterns not supported by the evidence.

## Output
Return a JSON object only (no markdown fences) with these exact fields:

```json
{
  "patterns": [
    {
      "title": "short pattern name under 60 characters",
      "description": "what this pattern means for the user",
      "evidence_summary": "key memories or events supporting this pattern",
      "durability": "emerging | established | declining",
      "confidence": 0.7,
      "actionable_suggestion": "optional proactive suggestion (empty string if none)"
    }
  ],
  "meta_observation": "one-sentence overall trajectory"
}
```

Important:
- Use the field names above exactly — `title` (not category), `evidence_summary` (not evidence), `actionable_suggestion` (not suggestion).
"""


def _build_discovery_prompt(
    memories: Sequence[AnyMemory],
    insights: Sequence[str],
    claims: Sequence[str],
    today: str,
) -> str:
    lines = [f"Analysis date: {today}", ""]

    lines.append("## Recent Memories (sorted by recency)")
    for mem in memories[:MAX_PROMPT_MEMORIES]:
        created = mem.created_at.strftime("%Y-%m-%d")
        lines.append(f"- [{created}] ({mem.memory_type}) {mem.content[:200]}")
    lines.append("")

    if insights:
        lines.append("## Consolidation Insights (from past maintenance cycles)")
        for ins in insights:
            lines.append(f"- {ins}")
        lines.append("")

    if claims:
        lines.append("## Knowledge Claims (from claim graph)")
        for cl in claims[:30]:
            lines.append(f"- {cl}")
        lines.append("")

    lines.append("Analyze these memories and identify cross-cycle behavioral patterns.")
    return "\n".join(lines)


__all__ = [
    "MAX_PROMPT_MEMORIES",
    "_SYSTEM_PROMPT",
    "_build_discovery_prompt",
]
