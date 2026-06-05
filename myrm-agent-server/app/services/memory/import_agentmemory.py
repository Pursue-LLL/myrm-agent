"""AgentMemory import adapter.

[INPUT]
AgentMemory JSON export payload with sessions, memories, summaries, observations, etc.

[OUTPUT]
MemoryImportDryRunResult mapping AgentMemory data to native semantic/episodic/procedural buckets.

[POS]
AgentMemory dry-run adapter extracted from import_adapters.py for single-responsibility.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory import (
    MemoryImportDryRunResult,
    MemoryImportMappingItem,
)

from app.services.memory.import_adapter_utils import (
    WARNING_ACCESS_LOGS_SKIPPED,
    WARNING_AGENTMEMORY_TOO_MANY_MEMORIES,
    WARNING_AGENTMEMORY_TOO_MANY_OBSERVATIONS,
    WARNING_AGENTMEMORY_TOO_MANY_SESSIONS,
    WARNING_AGENTMEMORY_TOO_MANY_SUMMARIES,
    WARNING_AGENTMEMORY_VERSION_UNSUPPORTED,
    WARNING_GRAPH_SKIPPED,
    build_metadata,
    build_result,
    float_between,
    iso_or_now,
    object_dict,
    strength_to_score,
    string_list,
    text,
    to_list,
    unsupported_result,
)

MAX_AGENTMEMORY_SESSIONS = 10_000
MAX_AGENTMEMORY_MEMORIES = 50_000
MAX_AGENTMEMORY_SUMMARIES = 10_000
MAX_AGENTMEMORY_OBSERVATIONS = 500_000
MIN_AGENTMEMORY_VERSION = (0, 3, 0)
MAX_AGENTMEMORY_VERSION = (0, 9, 99)


def dry_run_agentmemory(payload: dict[str, object]) -> MemoryImportDryRunResult:
    """Map an AgentMemory export into native memory buckets without persisting."""

    version = str(payload.get("version") or "")
    warnings: list[str] = []
    if not _is_supported_version(version):
        return unsupported_result("agentmemory", WARNING_AGENTMEMORY_VERSION_UNSUPPORTED)

    sessions = to_list(payload.get("sessions"))
    memories = to_list(payload.get("memories"))
    summaries = to_list(payload.get("summaries"))
    observations_by_session = object_dict(payload.get("observations")) if isinstance(payload.get("observations"), dict) else {}
    semantic_memories = to_list(payload.get("semanticMemories"))
    procedural_memories = to_list(payload.get("proceduralMemories"))

    observation_count = sum(len(value) for value in observations_by_session.values() if isinstance(value, list))
    if len(sessions) > MAX_AGENTMEMORY_SESSIONS:
        return unsupported_result("agentmemory", WARNING_AGENTMEMORY_TOO_MANY_SESSIONS)
    if len(memories) + len(semantic_memories) > MAX_AGENTMEMORY_MEMORIES:
        return unsupported_result("agentmemory", WARNING_AGENTMEMORY_TOO_MANY_MEMORIES)
    if len(summaries) > MAX_AGENTMEMORY_SUMMARIES:
        return unsupported_result("agentmemory", WARNING_AGENTMEMORY_TOO_MANY_SUMMARIES)
    if observation_count > MAX_AGENTMEMORY_OBSERVATIONS:
        return unsupported_result("agentmemory", WARNING_AGENTMEMORY_TOO_MANY_OBSERVATIONS)

    normalized: dict[str, list[dict[str, object]]] = {
        "semantic": [],
        "episodic": [],
        "procedural": [],
    }
    normalized["semantic"].extend(_memory_to_semantic(item) for item in memories if isinstance(item, dict))
    normalized["semantic"].extend(_semantic_to_semantic(item) for item in semantic_memories if isinstance(item, dict))
    summary_mapped = len([item for item in summaries if isinstance(item, dict)])
    observation_mapped = 0
    normalized["episodic"].extend(_summary_to_episodic(item) for item in summaries if isinstance(item, dict))
    for session_id, raw_entries in observations_by_session.items():
        if not isinstance(raw_entries, list):
            continue
        observation_mapped += len([entry for entry in raw_entries if isinstance(entry, dict)])
        normalized["episodic"].extend(
            _observation_to_episodic(session_id, entry) for entry in raw_entries if isinstance(entry, dict)
        )
    normalized["procedural"].extend(_procedural_to_procedural(item) for item in procedural_memories if isinstance(item, dict))
    normalized = {bucket: entries for bucket, entries in normalized.items() if entries}

    mappings = [
        MemoryImportMappingItem(
            source_bucket="memories",
            target_bucket="semantic",
            status="mapped",
            item_count=len(memories),
            imported_count=len([item for item in memories if isinstance(item, dict)]),
        ),
        MemoryImportMappingItem(
            source_bucket="semanticMemories",
            target_bucket="semantic",
            status="mapped",
            item_count=len(semantic_memories),
            imported_count=len([item for item in semantic_memories if isinstance(item, dict)]),
        ),
        MemoryImportMappingItem(
            source_bucket="summaries",
            target_bucket="episodic",
            status="mapped",
            item_count=len(summaries),
            imported_count=summary_mapped,
        ),
        MemoryImportMappingItem(
            source_bucket="observations",
            target_bucket="episodic",
            status="mapped",
            item_count=observation_count,
            imported_count=observation_mapped,
        ),
        MemoryImportMappingItem(
            source_bucket="proceduralMemories",
            target_bucket="procedural",
            status="mapped",
            item_count=len(procedural_memories),
            imported_count=len([item for item in procedural_memories if isinstance(item, dict)]),
        ),
    ]

    mapped_items = sum(mapping.imported_count for mapping in mappings)
    unmapped_items = (
        len(memories) + len(semantic_memories) + len(summaries) + observation_count + len(procedural_memories) - mapped_items
    )
    if payload.get("graphNodes") or payload.get("graphEdges"):
        warnings.append(WARNING_GRAPH_SKIPPED)
    if payload.get("accessLogs"):
        warnings.append(WARNING_ACCESS_LOGS_SKIPPED)

    return build_result(
        source="agentmemory",
        version=version,
        normalized=normalized,
        mappings=mappings,
        mapped_items=mapped_items,
        unmapped_items=max(unmapped_items, 0),
        warnings=warnings,
    )


def _is_supported_version(version: str) -> bool:
    parts = version.split(".")
    if len(parts) != 3:
        return False
    try:
        parsed = tuple(int(part) for part in parts)
    except ValueError:
        return False
    return MIN_AGENTMEMORY_VERSION <= parsed <= MAX_AGENTMEMORY_VERSION


def _memory_to_semantic(item: dict[object, object]) -> dict[str, object]:
    typed = object_dict(item)
    title = text(typed.get("title"))
    content = text(typed.get("content")) or title
    return {
        "content": f"{title}\n{content}".strip() if title and title not in content else content,
        "importance": strength_to_score(typed.get("strength")),
        "confidence": 0.85,
        "tags": string_list(typed.get("concepts")) + [text(typed.get("type"))],
        "created_at": iso_or_now(typed.get("createdAt")),
        "updated_at": iso_or_now(typed.get("updatedAt")),
        "metadata": build_metadata(
            "agentmemory",
            typed,
            ("id", "type", "files", "sessionIds", "version", "isLatest", "forgetAfter"),
        ),
    }


def _semantic_to_semantic(item: dict[object, object]) -> dict[str, object]:
    typed = object_dict(item)
    return {
        "content": text(typed.get("fact")),
        "importance": strength_to_score(typed.get("strength")),
        "confidence": float_between(typed.get("confidence"), 0.85),
        "created_at": iso_or_now(typed.get("createdAt")),
        "updated_at": iso_or_now(typed.get("updatedAt")),
        "metadata": build_metadata("agentmemory", typed, ("id", "sourceSessionIds", "sourceMemoryIds", "accessCount")),
    }


def _summary_to_episodic(item: dict[object, object]) -> dict[str, object]:
    typed = object_dict(item)
    parts = [
        text(typed.get("title")),
        text(typed.get("narrative")),
        "; ".join(string_list(typed.get("keyDecisions"))),
    ]
    return {
        "content": "\n".join(part for part in parts if part),
        "event_type": "agentmemory_session_summary",
        "timestamp": iso_or_now(typed.get("createdAt")),
        "related_entities": string_list(typed.get("concepts")),
        "importance": 0.7,
        "metadata": build_metadata("agentmemory", typed, ("sessionId", "project", "filesModified", "observationCount")),
    }


def _observation_to_episodic(session_id: str, item: dict[object, object]) -> dict[str, object]:
    typed = object_dict(item)
    facts = "; ".join(string_list(typed.get("facts")))
    parts = [text(typed.get("title")), text(typed.get("narrative")), facts]
    return {
        "content": "\n".join(part for part in parts if part),
        "event_type": f"agentmemory_{text(typed.get('type')) or 'observation'}",
        "timestamp": iso_or_now(typed.get("timestamp")),
        "related_entities": string_list(typed.get("concepts")),
        "importance": float_between(typed.get("importance"), 5.0) / 10,
        "metadata": build_metadata("agentmemory", typed, ("id", "sessionId", "files", "confidence"))
        | {"source_session_id": session_id},
    }


def _procedural_to_procedural(item: dict[object, object]) -> dict[str, object]:
    typed = object_dict(item)
    name = text(typed.get("name"))
    steps = string_list(typed.get("steps"))
    action = "\n".join(steps) if steps else text(typed.get("expectedOutcome")) or name
    return {
        "content": f"{name}\n{action}".strip() if name else action,
        "trigger": text(typed.get("triggerCondition")) or "Imported agentmemory procedure",
        "action": action or "Review imported procedure",
        "priority": int(strength_to_score(typed.get("strength")) * 10),
        "trigger_keywords": string_list(typed.get("concepts")),
        "created_at": iso_or_now(typed.get("createdAt")),
        "updated_at": iso_or_now(typed.get("updatedAt")),
        "metadata": build_metadata("agentmemory", typed, ("id", "sourceSessionIds", "sourceObservationIds", "frequency")),
    }
