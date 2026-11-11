"""Internal approval helpers for MemoryManager.


[INPUT]
- memory.types::{AnyMemory, SemanticMemory, EpisodicMemory, ProceduralMemory, PendingRecord, MemoryType} (POS: memory data models)
- memory._internal.storage::InvalidPendingEditError (POS: memory error hierarchy)
- memory._internal.rule_text::{RuleFields, edited_rule_fields} (POS: the trigger, action and content a queued rule holds once the reviewer rewords it)

[OUTPUT]
- memory_to_pending: AnyMemory → PendingRecord serialization
- pending_to_memory: PendingRecord → AnyMemory deserialization
- apply_edited_content: reviewer-edited wording applied to a PendingRecord (a rule's trigger and action follow it)

[POS]
Approval queue helpers. Handles AnyMemory ↔ PendingRecord conversion for the approval
pipeline. Internal only — not part of the public API.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory._internal.rule_text import RuleFields, edited_rule_fields
from myrm_agent_harness.toolkits.memory._internal.storage import InvalidPendingEditError
from myrm_agent_harness.toolkits.memory.types import (
    AnyMemory,
    ConversationMemory,
    EpisodicMemory,
    MemoryType,
    PendingRecord,
    PendingResolutionAction,
    ProceduralMemory,
    SemanticMemory,
)


def _origin_chat_id(memory: AnyMemory) -> str | None:
    """The chat a memory was written from: a field on vector-backed memories, a metadata entry on a rule."""
    if isinstance(memory, ProceduralMemory):
        chat_id = memory.metadata.get("source_chat_id")
        return str(chat_id) if chat_id else None
    return getattr(memory, "source_chat_id", None)


def memory_to_pending(
    memory: AnyMemory,
    *,
    resolution_action: PendingResolutionAction = PendingResolutionAction.STORE,
    target_memory_id: str | None = None,
    target_content: str | None = None,
) -> PendingRecord:
    """Serialise an AnyMemory into a PendingRecord for the approval queue.

    ``resolution_action``/``target_memory_id`` describe what approving the record
    should do: persist it as-is (``STORE``), replace the targeted memory with it
    (``CORRECT``), or retire the targeted memory (``DELETE``). ``target_content``
    is the reviewed memory's content, kept so the approval surface can show the
    user exactly which memory will be replaced or removed.
    """
    data = memory.model_dump(exclude={"embedding"}, mode="json")
    return PendingRecord(
        id=memory.id,
        memory_type=MemoryType(memory.memory_type),
        content=memory.content,
        memory_data=data,
        source_chat_id=_origin_chat_id(memory),
        source_message_id=getattr(memory, "source_message_id", None),
        resolution_action=resolution_action,
        target_memory_id=target_memory_id,
        target_content=target_content,
    )


def apply_edited_content(record: PendingRecord, edited_content: str) -> PendingRecord:
    """Return ``record`` carrying the reviewer's reworded text.

    Both ``content`` (used by ``CORRECT``) and ``memory_data["content"]`` (used to
    rebuild the memory for ``STORE``) are updated so every approval path persists
    the same wording. The exact-fact identifiers stamped on the proposed wording no
    longer describe the reworded text, so they are cleared and derived again from the
    text that is stored. A proposed rule is stored from its ``trigger`` and ``action``
    (the prompt reads those), so they follow the reworded text as an edit of a stored
    rule would (see ``rule_text``). Profile entries and ``DELETE`` proposals persist no
    free text, so an edit there is an error rather than a silently dropped change.

    Raises:
        InvalidPendingEditError: the edit is blank or the proposal has no editable text.
    """
    content = edited_content.strip()
    if not content:
        raise InvalidPendingEditError("Edited content must not be empty")
    if record.memory_type == MemoryType.PROFILE or record.resolution_action == PendingResolutionAction.DELETE:
        raise InvalidPendingEditError("This proposal has no editable content")
    if content == record.content:
        return record
    reworded_data = {**record.memory_data, "content": content, "exact_identifiers": []}
    if record.memory_type == MemoryType.PROCEDURAL:
        held = RuleFields(
            str(record.memory_data.get("trigger", "")), str(record.memory_data.get("action", "")), record.content
        )
        rule = edited_rule_fields(held, content)
        reworded_data.update(trigger=rule.trigger, action=rule.action, content=rule.content)
        content = rule.content
    return record.model_copy(update={"content": content, "memory_data": reworded_data})


def pending_to_memory(record: PendingRecord) -> AnyMemory:
    """Reconstruct an AnyMemory from a PendingRecord."""
    data = dict(record.memory_data)
    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        # Metadata holds scalars only; identifier lists belong to the typed ``exact_identifiers`` field.
        data["metadata"] = {key: value for key, value in metadata.items() if not isinstance(value, list)}
    mt = record.memory_type
    if mt == MemoryType.SEMANTIC:
        return SemanticMemory.model_validate(data)
    if mt == MemoryType.EPISODIC:
        return EpisodicMemory.model_validate(data)
    if mt == MemoryType.PROCEDURAL:
        return ProceduralMemory.model_validate(data)
    if mt == MemoryType.CONVERSATION:
        return ConversationMemory.model_validate(data)
    raise ValueError(f"Cannot reconstruct memory from type: {mt}")
