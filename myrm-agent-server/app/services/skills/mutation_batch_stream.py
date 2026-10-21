"""Stream contract between the skill_manage batch hook and the Task Steps entry of the call.

The harness streams a tool call's arguments as its Task Steps entry and never the tool result, so the batch a
call commits cannot be read back from the step. The hook announces the batch as its own event instead, and the
stream collector (and the chat store in the frontend) link it to the step that is still waiting for one.

[INPUT]
- myrm_agent_harness.core.events.types::AgentEventType (POS: SSE event type names)
- app.services.skills.skill_manage_batch_parse::is_skill_manage_tool_name (POS: namespaced tool-name match)
[OUTPUT]
- BATCH_ID_FIELD: key carrying the batch id on the event and on the linked step
- build_batch_committed_event: the event the hook pushes through the tool progress sink
- link_batch_to_step: attach the event's batch id to the step awaiting it
[POS]
Dependency-free contract module shared by the hook (producer) and stream_collector (consumer).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from myrm_agent_harness.core.events.types import AgentEventType

from app.services.skills.skill_manage_batch_parse import is_skill_manage_tool_name

BATCH_ID_FIELD = "skill_mutation_batch_id"
_TOOL_NAME = "skill_manage_tool"
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", re.IGNORECASE)
_FAILED_STATUSES = frozenset({"error", "cancelled"})


def build_batch_committed_event(batch_id: str) -> dict[str, object]:
    """The event announcing that the running skill_manage call committed ``batch_id``."""
    return {"type": AgentEventType.TOOL_END.value, "tool_name": _TOOL_NAME, BATCH_ID_FIELD: batch_id}


def link_batch_to_step(steps: Sequence[dict[str, object]], event: Mapping[str, object]) -> bool:
    """Attach the batch id carried by ``event`` to the latest skill_manage step that has none yet.

    A batch is announced while its call is still running, so the step awaiting it is the newest one that
    neither failed nor already owns a batch. Returns whether a step was linked.
    """
    batch_id = event.get(BATCH_ID_FIELD)
    if not isinstance(batch_id, str) or not _UUID_RE.fullmatch(batch_id.strip()):
        return False
    if not is_skill_manage_tool_name(event.get("tool_name")):
        return False
    for step in reversed(steps):
        if (
            is_skill_manage_tool_name(step.get("tool_name"))
            and not step.get(BATCH_ID_FIELD)
            and step.get("status") not in _FAILED_STATUSES
        ):
            step[BATCH_ID_FIELD] = batch_id.strip().lower()
            return True
    return False
