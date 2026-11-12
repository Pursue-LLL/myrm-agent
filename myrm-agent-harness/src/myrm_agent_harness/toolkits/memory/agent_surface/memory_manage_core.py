"""Memory manage actions addressed by memory id alone, shared by the agent tool and the MCP adapter.

A memory's type is a property of the memory, not an argument: the id is the only address a caller
supplies, and the stored memory decides which store an action reaches and which actions apply. The
lookup runs through the manager's namespaces, so an id outside the caller's scope is reported as
not found.

[INPUT]
- toolkits.memory.manager::MemoryManager (POS: memory lifecycle manager; protected memories are never touched by the agent)
- toolkits.memory.types::MemoryType (POS: memory type enum)

[OUTPUT]
- ManageAction: the supported action names as a Literal
- MANAGE_ACTIONS: the same names as a tuple
- manage_memory: run one action on an existing memory and return the model-facing result

[POS]
Single implementation of update / delete / correct / rate for ``memory_agent_tools.manage_tool`` and
``mcp_server.manage_tool``. Failures the manager raises propagate; each surface translates them with
``write_failure_feedback``. An update reply says so when the importance it was given did not reach the stored memory, and a correct reply on a
rule points the caller to update.
"""

from __future__ import annotations

from typing import Literal, get_args

from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.types import AnyMemory, MemoryType

ManageAction = Literal["update", "delete", "correct", "rate"]
MANAGE_ACTIONS: tuple[ManageAction, ...] = get_args(ManageAction)

# The vector-backed types an agent can rate or delete, named the way recall labels them.
_VECTOR_LABELS: dict[MemoryType, str] = {MemoryType.SEMANTIC: "knowledge", MemoryType.EPISODIC: "event"}


def _vector_collection(manager: MemoryManager, mem_type: MemoryType) -> str:
    config = manager.config
    return config.semantic_collection if mem_type == MemoryType.SEMANTIC else config.episodic_collection


async def _rate(manager: MemoryManager, mem_type: MemoryType, memory_id: str, rating_score: int | None) -> str:
    if rating_score is None:
        return "Rate requires 'rating_score' (1-5)."
    if mem_type not in _VECTOR_LABELS:
        return "Rate action is only supported for knowledge/event memories."
    # Type-enabled, not dense-capable: without an embedding backend the type
    # lives in the BM25 sparse mirror and stays rateable.
    if mem_type not in manager.get_enabled_types():
        return f"{_VECTOR_LABELS[mem_type]} memory is not enabled."
    if await manager.rate_memory(memory_id, rating_score):
        return f"Memory rated (ID: {memory_id}, score: {rating_score})"
    return f"Memory not found (ID: {memory_id})"


async def _delete(manager: MemoryManager, mem_type: MemoryType, memory_id: str) -> str:
    if mem_type in _VECTOR_LABELS:
        if mem_type not in manager.get_enabled_types():
            return f"{_VECTOR_LABELS[mem_type]} memory is not enabled."
        deleted = await manager.delete_memory(_vector_collection(manager, mem_type), [memory_id], allow_protected=False)
        if deleted > 0:
            return f"Memory deleted (ID: {memory_id})"
        return (
            f"Cannot delete memory (ID: {memory_id}): "
            "it may be protected by the user or not found. Protected memories cannot be deleted by the agent."
        )

    if mem_type == MemoryType.PROCEDURAL:
        if not manager.has_relational:
            return "Procedural memory is not enabled."
        if await manager.delete_rule(memory_id, allow_protected=False):
            return f"Rule deleted (ID: {memory_id})"
        return (
            f"Cannot delete rule (ID: {memory_id}): "
            "it may be user-protected or not found. Rules the user explicitly "
            "locked cannot be deleted by the agent."
        )

    return f"Delete action is not supported for {mem_type.value} memories."


def _agent_may_modify(memory: AnyMemory) -> bool:
    """``is_exact_fact`` is the classifier's stamp; only an explicit pin or lock is the user's decision."""
    return not (memory.pinned or memory.is_user_locked)


def _unstored_importance_note(updated: AnyMemory, requested: float | None) -> str:
    """Say so when the importance the caller asked for is not what the updated memory holds.

    The stored result decides, not a list of types: a memory type that cannot take the value drops it silently, and
    a reply that only says "updated" would let the model tell the user the importance changed.
    """
    if requested is None or getattr(updated, "importance", None) == requested:
        return ""
    return "Importance was not changed: only knowledge and event memories store it."


async def _update(
    manager: MemoryManager, memory: AnyMemory, new_content: str | None, new_importance: float | None
) -> str:
    if not new_content:
        return "Update requires 'new_content'."
    updated = await manager.update_memory(
        memory.id,
        content=new_content,
        importance=new_importance,
        allow_protected=_agent_may_modify(memory),
    )
    reply = f"Memory updated (ID: {updated.id})"
    note = _unstored_importance_note(updated, new_importance)
    return f"{reply}. {note}" if note else reply


async def _correct(manager: MemoryManager, memory: AnyMemory, new_content: str | None) -> str:
    if not new_content:
        return "Correct requires 'new_content' with the corrected fact."
    if memory.memory_type != MemoryType.SEMANTIC:
        reply = "Correct action is only supported for knowledge memories."
        if memory.memory_type == MemoryType.PROCEDURAL:
            # A rule deleted and saved again waits for the user's approval while the old one is already gone.
            reply += " To change a rule, use update with new_content."
        return reply
    if MemoryType.SEMANTIC not in manager.get_enabled_types():
        return "Knowledge memory is not enabled."
    correction = await manager.correct_memory(memory.id, new_content, allow_protected=_agent_may_modify(memory))
    return f"Memory corrected (new ID: {correction.id}). Prior entry {memory.id} kept in history."


async def manage_memory(
    manager: MemoryManager,
    *,
    action: str,
    memory_id: str,
    new_content: str | None = None,
    new_importance: float | None = None,
    rating_score: int | None = None,
) -> str:
    """Apply ``action`` to the memory ``memory_id`` and return the text the model should see."""
    memory = await manager.get_memory(memory_id)
    if memory is None:
        return f"Memory not found (ID: {memory_id})"
    mem_type = memory.memory_type

    if action == "rate":
        return await _rate(manager, mem_type, memory_id, rating_score)
    if action == "delete":
        return await _delete(manager, mem_type, memory_id)
    if action == "update":
        return await _update(manager, memory, new_content, new_importance)
    if action == "correct":
        return await _correct(manager, memory, new_content)
    return f"Unknown action: {action}"
