"""Parse skill_manage_tool batch_id for progress step enrichment.

[INPUT]
- Progress step dict from stream_collector tasks_steps merge

[OUTPUT]
- extract_skill_mutation_batch_id_from_step: UUID when batch succeeded

[POS]
Server-side parser; keeps frontend free of tool output regex.
"""

from __future__ import annotations

import json
import re
from typing import Any

_SKILL_MANAGE_TOOL_SUFFIX = "skill_manage_tool"
_SKILL_BATCH_JSON_PREFIX = "myrm_skill_batch:"
_BATCH_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_BATCH_ID_RE = re.compile(
    r"batch_id=([0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})",
    re.IGNORECASE,
)
_SUCCESS_MARKERS = ("Batch applied successfully", "batch applied successfully")


def is_skill_manage_tool_name(tool_name: object | None) -> bool:
    if not isinstance(tool_name, str) or not tool_name.strip():
        return False
    name = tool_name.strip()
    return name == _SKILL_MANAGE_TOOL_SUFFIX or name.endswith(_SKILL_MANAGE_TOOL_SUFFIX)


def _collect_text_chunks(items: object, stdout: object | None) -> list[str]:
    chunks: list[str] = []
    if isinstance(items, str):
        chunks.append(items)
    elif isinstance(items, list):
        for entry in items:
            if isinstance(entry, dict):
                text = entry.get("text")
                if isinstance(text, str):
                    chunks.append(text)
            elif isinstance(entry, str):
                chunks.append(entry)
    if isinstance(stdout, str) and stdout.strip():
        chunks.append(stdout)
    return chunks


def _batch_id_from_structured_footer(chunk: str) -> str | None:
    for line in chunk.splitlines():
        stripped = line.strip()
        if not stripped.startswith(_SKILL_BATCH_JSON_PREFIX):
            continue
        try:
            data = json.loads(stripped[len(_SKILL_BATCH_JSON_PREFIX) :])
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        batch_id = data.get("batch_id")
        if isinstance(batch_id, str) and _BATCH_UUID_RE.fullmatch(batch_id.strip()):
            return batch_id.strip().lower()
    return None


def extract_skill_mutation_batch_id_from_step(step: dict[str, Any]) -> str | None:
    """Return batch UUID when a successful skill_manage step output includes it."""
    if not is_skill_manage_tool_name(step.get("tool_name")):
        return None
    status = step.get("status")
    if status in ("error", "cancelled") or step.get("error"):
        return None

    for chunk in _collect_text_chunks(step.get("items"), step.get("stdout")):
        if not any(marker in chunk for marker in _SUCCESS_MARKERS):
            continue
        structured = _batch_id_from_structured_footer(chunk)
        if structured:
            return structured
        match = _BATCH_ID_RE.search(chunk)
        if match:
            return match.group(1).lower()
    return None
