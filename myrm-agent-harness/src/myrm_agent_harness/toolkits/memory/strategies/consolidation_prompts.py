"""System and user prompts for cross-session memory consolidation.

[INPUT]
- memory.types::AnyMemory (POS: memory data models)

[OUTPUT]
- _SYSTEM_PROMPT: Base system instructions for memory consolidation, declaring the exact output JSON field names
- _build_user_prompt: Serializes memories to compact user prompt with short IDs
- _build_id_map: Maps compact short IDs to full UUIDs

[POS]
Prompts and payload compression helpers for memory consolidation.
Enforces Class-First Rubric and preserves Prompt Cache static prefixes.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.types import AnyMemory

_SYSTEM_PROMPT = """You are a memory consolidation agent. Analyze the user's memories (semantic facts and episodic events) and identify:

1. **Contradictions**: Memories that conflict (e.g., "prefers Python" vs "prefers Rust")
2. **Redundancies**: Multiple memories expressing the same fact → merge into one
3. **Date conversion**: Relative dates ("yesterday", "last week") → absolute dates (YYYY-MM-DD)
4. **Enrichment**: Fragmented memories that can be combined into a richer single memory
5. **Stale corrections**: When multiple corrections exist on the same topic (indicated by `corrects:` or similar `source_error`), keep the newest correction and demote older ones via update_content (set importance to 0.05)

## Rubric (Class-First 评分标准)
Before proposing any consolidation operation, strictly evaluate it against these dimensions:
1. **准确性 (Accuracy)**: Does the merged/updated memory accurately reflect the underlying truth without hallucination?
2. **防碎片化 (Anti-fragmentation)**: Does this operation combine fragmented pieces into a cohesive, complete whole?
3. **冗余度 (Redundancy)**: Does this operation successfully eliminate duplicate or overlapping information?

## Rules
- Only output actions when there is clear evidence. Do NOT fabricate connections.
- Preserve all unique information when merging. Never discard details.
- Use absolute dates based on today's date provided below.
- Keep the original language (Chinese stays Chinese, English stays English).
- Memories tagged [NEW] are recently added. Pay special attention to contradictions between [NEW] and existing memories.

## Output
Return a JSON object only (no markdown fences) with exactly these fields:

```json
{
  "operations": [
    {
      "action": "merge",
      "source_ids": ["<short id>", "<short id>"],
      "merged_content": "<one memory that keeps every unique detail of its sources>",
      "importance": 0.7,
      "accuracy_score": 0.9,
      "anti_fragmentation_score": 0.9,
      "redundancy_score": 0.9,
      "reasoning": "<one sentence on why these memories belong together>"
    },
    {
      "action": "correct",
      "memory_id": "<short id>",
      "corrected_content": "<the memory with its outdated or wrong statement replaced>",
      "importance": 0.5,
      "accuracy_score": 0.9,
      "anti_fragmentation_score": 0.9,
      "redundancy_score": 0.9,
      "reasoning": "<one sentence on what was wrong>"
    },
    {
      "action": "update_content",
      "memory_id": "<short id>",
      "new_content": "<the memory rewritten, for example with relative dates made absolute>",
      "accuracy_score": 0.9,
      "anti_fragmentation_score": 0.9,
      "redundancy_score": 0.9,
      "reasoning": "<one sentence on why the rewrite is needed>"
    }
  ],
  "insights": ["<one plain-text sentence per durable observation about the user>"]
}
```

Important:
- Everything in angle brackets is a placeholder for real content; never copy example text into a reply.
- `action` is exactly `merge`, `correct` or `update_content`. Include only the operations you need; return `{"operations": [], "insights": []}` when nothing needs consolidating.
- Refer to a memory by the short id in square brackets in the list (write `a1b2c3d4`, not `[a1b2c3d4]`). A `merge` needs at least two `source_ids`. Name each memory in at most one operation.
- The three scores are your honest rubric scores from 0.0 to 1.0; low-scoring operations are discarded. `importance` is optional (0.0 to 1.0): on `update_content` set it only to demote a superseded memory, otherwise leave it out.
- Write numbers as plain JSON numbers and leave an optional field out instead of writing null.
- Ports, IP addresses, URLs, environment variable names and file paths in the sources must appear unchanged in the result of a `merge` or `update_content`. A `correct` may drop or change one only if its `reasoning` quotes that value.
- `insights` holds plain strings, never objects; use an empty list when there is no durable observation.
"""


def _build_user_prompt(
    memories: Sequence[AnyMemory],
    today: str,
    id_map: dict[str, str],
    new_ids: frozenset[str] | None = None,
) -> str:
    """Build user prompt with short IDs to save tokens (~28 tokens per memory)."""
    reverse_map = {v: k for k, v in id_map.items()}
    lines = [f"Today's date: {today}", "", "## Memories to analyze", ""]
    for mem in memories:
        short_id = reverse_map.get(mem.id, mem.id[:8])
        tag = " [NEW]" if new_ids and mem.id in new_ids else ""
        meta_parts = [f"type={mem.memory_type}"]
        if hasattr(mem, "importance"):
            meta_parts.append(f"importance={mem.importance:.1f}")
        if hasattr(mem, "confidence"):
            meta_parts.append(f"confidence={mem.confidence:.1f}")
        meta_parts.append(f"created={mem.created_at.strftime('%Y-%m-%d %H:%M')}")
        correction_of = getattr(mem, "correction_of", None)
        if correction_of:
            corrects_short = reverse_map.get(correction_of, correction_of[:8])
            meta_parts.append(f"corrects:{corrects_short}")
        lines.append(f"[{short_id}]{tag} ({', '.join(meta_parts)})")
        lines.append(f"  {mem.content}")
        source_error = getattr(mem, "source_error", None)
        if source_error:
            lines.append(f"  source_error: {source_error}")
        lines.append("")
    lines.append("Analyze these memories and output a JSON object with operations and insights.")
    return "\n".join(lines)


def _build_id_map(memories: Sequence[AnyMemory]) -> dict[str, str]:
    """Build short_id → full_id mapping. Uses first 8 chars, extends on collision."""
    id_map: dict[str, str] = {}
    used_shorts: set[str] = set()
    for mem in memories:
        short = mem.id[:8]
        length = 8
        while short in used_shorts and length < len(mem.id):
            length += 4
            short = mem.id[:length]
        id_map[short] = mem.id
        used_shorts.add(short)
    return id_map


__all__ = [
    "_SYSTEM_PROMPT",
    "_build_id_map",
    "_build_user_prompt",
]
