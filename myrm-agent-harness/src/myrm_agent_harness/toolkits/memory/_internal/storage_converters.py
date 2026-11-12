"""Vector Document <-> Memory Schema converters and shared metadata helpers.

[INPUT]
- memory.protocols.vector::{VectorDocument, FilterDict} (POS: vector store protocol and data models)
- memory.types::{SemanticMemory, EpisodicMemory, ...} (POS: memory data models)
- memory.domain_types::{MemoryDomain, DomainCategory} (POS: domain & category taxonomy)
- _internal.store_stamp::{STORED_TS_KEY, stored_at_from_metadata, stored_ts_payload} (POS: arrival stamp of a stored memory and its payload form)

[OUTPUT]
- Scope helpers: _scope_payload, _scope_from_metadata, _user_filter
- Lifecycle helpers: _lifecycle_payload, _lifecycle_from_metadata
- Usage-stamp helper: _stamp_access (records one use on a stored document)
- semantic_to_doc, episodic_to_doc: SemanticMemory / EpisodicMemory to VectorDocument
- doc_to_semantic, doc_to_episodic: VectorDocument to SemanticMemory / EpisodicMemory

[POS]
Stateless conversion layer between vector-store documents and typed memory models. A document's store stamp
travels with the memory in both directions, so a rewrite through a model keeps the stamp it was stored with.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

from myrm_agent_harness.toolkits.memory._internal._storage_payload_helpers import (
    _last_accessed_from_metadata,
    _last_accessed_payload,
    _lifecycle_from_metadata,
    _lifecycle_payload,
    _safe_float,
    _safe_int,
    _scope_from_metadata,
    _scope_payload,
    _stamp_access,
    _status_from_metadata,
    _user_filter,
)
from myrm_agent_harness.toolkits.memory._internal.store_stamp import (
    STORED_TS_KEY,
    stored_at_from_metadata,
    stored_ts_payload,
)
from myrm_agent_harness.toolkits.memory.domain_types import MemoryDomain
from myrm_agent_harness.toolkits.memory.protocols.vector import (
    VectorDocument,
)
from myrm_agent_harness.toolkits.memory.types import (
    EpisodicMemory,
    MemoryType,
    PreferenceType,
    SemanticMemory,
)

logger = logging.getLogger(__name__)

__all__ = [
    "_safe_float",
    "_safe_int",
    "_status_from_metadata",
    "_user_filter",
    "_scope_payload",
    "_scope_from_metadata",
    "_lifecycle_payload",
    "_lifecycle_from_metadata",
    "_stamp_access",
    "doc_to_semantic",
    "doc_to_episodic",
    "semantic_to_doc",
    "episodic_to_doc",
]

# Payload keys that have a dedicated model attribute, so they must not also be
# copied into ``metadata``. Only list a key here when ``doc_to_*`` actually
# assigns it onto the model — keys listed here but never assigned are silently
# dropped on every read/write round-trip. ``archived_at`` and ``archive_reason``
# intentionally stay out so they persist through ``metadata`` unchanged.
_COMMON_KNOWN_KEYS = frozenset(
    {
        "user_id",
        "memory_type",
        "importance",
        "source_chat_id",
        "access_count",
        "user_rating",
        "pinned",
        "status",
        "archived",
        "expected_valid_days",
        "created_at",
        "updated_at",
        "language",
        "merge_count",
        "merge_history",
        "primary_namespace",
        "namespaces",
        "agent_id",
        "channel_id",
        "conversation_id",
        "task_id",
        "memory_tier",
        "digest_kind",
        "evaporation_state",
        "evaporated_at",
        "claim_graph_state",
        "claim_graph_node_id",
        "claim_graph_updated_at",
        "claim_graph_conflict",
        "summary_l0",
        "overview_l1",
        "domain",
        "domain_category",
    }
)

_SEMANTIC_KNOWN_KEYS = _COMMON_KNOWN_KEYS | frozenset(
    {
        "confidence",
        "is_exact_fact",
        "exact_identifiers",
        "preference_type",
        "preference_strength",
        "correction_of",
        "source_error",
        "tags",
        "source_chat_ids",
        "last_accessed_at",
        STORED_TS_KEY,
    }
)

_EPISODIC_KNOWN_KEYS = _COMMON_KNOWN_KEYS | frozenset(
    {
        "event_type",
        "related_entities",
        "tags",
        "source_chat_ids",
        "last_accessed_at",
        STORED_TS_KEY,
    }
)


def _parse_domain(raw_domain: object) -> MemoryDomain:
    try:
        return MemoryDomain(str(raw_domain))
    except (ValueError, TypeError):
        return MemoryDomain.USER


def _string_list_from_metadata(meta: Mapping[str, object], key: str) -> list[str]:
    """Restore a list-valued payload key (tags, related entities, source chats) as strings.

    The payload keeps tags and entities under single keys, which are excluded
    from the free-form ``extra`` metadata, so a read that skips them loses the
    tag filter / tag statistics and the entity graph edges for every memory.
    """
    raw = meta.get(key)
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(item) for item in raw if str(item).strip()]


def doc_to_semantic(doc: VectorDocument) -> SemanticMemory:
    """Convert VectorDocument to SemanticMemory."""
    meta = doc.metadata
    raw_pref = meta.get("preference_type")
    pref_type: PreferenceType | None = (
        "explicit" if raw_pref == "explicit" else "implicit" if raw_pref == "implicit" else None
    )
    raw_corr = str(meta.get("correction_of", ""))
    extra: dict[str, str | int | float | bool] = {}
    for k, v in meta.items():
        if k not in _SEMANTIC_KNOWN_KEYS and isinstance(v, (str, int, float, bool)):
            extra[k] = v
    raw_evd = _safe_int(meta.get("expected_valid_days", 0))
    evd: int | None = raw_evd if raw_evd > 0 else None

    return SemanticMemory(
        id=doc.id,
        user_id=str(meta.get("user_id", "")),
        content=doc.content,
        embedding=doc.vector,
        importance=_safe_float(meta.get("importance", 0.5), 0.5),
        confidence=_safe_float(meta.get("confidence", 1.0), 1.0),
        source_chat_id=str(meta.get("source_chat_id", "")) or None,
        preference_type=pref_type,
        preference_strength=_safe_float(meta.get("preference_strength", 0.0)),
        correction_of=raw_corr or None,
        source_error=str(meta.get("source_error", "")) or None,
        access_count=_safe_int(meta.get("access_count", 0)),
        last_accessed_at=_last_accessed_from_metadata(meta),
        user_rating=_safe_float(meta.get("user_rating", 0.5), 0.5),
        pinned=bool(meta.get("pinned", False)),
        is_exact_fact=meta.get("is_exact_fact") is True,
        exact_identifiers=_string_list_from_metadata(meta, "exact_identifiers"),
        status=_status_from_metadata(meta),
        expected_valid_days=evd,
        metadata=extra,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        stored_at=stored_at_from_metadata(meta),
        language="zh" if meta.get("language") == "zh" else "en",
        merge_count=_safe_int(meta.get("merge_count", 0)),
        merge_history=str(meta.get("merge_history", "")),
        scope=_scope_from_metadata(meta),
        lifecycle=_lifecycle_from_metadata(meta),
        summary_l0=str(meta.get("summary_l0", "")),
        overview_l1=str(meta.get("overview_l1", "")),
        domain=_parse_domain(meta.get("domain")),
        domain_category=str(meta.get("domain_category", "")),
        tags=_string_list_from_metadata(meta, "tags"),
        source_chat_ids=_string_list_from_metadata(meta, "source_chat_ids"),
    )


def doc_to_episodic(doc: VectorDocument) -> EpisodicMemory:
    """Convert VectorDocument to EpisodicMemory."""
    meta = doc.metadata
    extra: dict[str, str | int | float | bool] = {}
    for k, v in meta.items():
        if k not in _EPISODIC_KNOWN_KEYS and isinstance(v, (str, int, float, bool)):
            extra[k] = v
    raw_evd = _safe_int(meta.get("expected_valid_days", 0))
    evd: int | None = raw_evd if raw_evd > 0 else None

    return EpisodicMemory(
        id=doc.id,
        user_id=str(meta.get("user_id", "")),
        content=doc.content,
        embedding=doc.vector,
        event_type=str(meta.get("event_type", "conversation")),
        importance=_safe_float(meta.get("importance", 0.5), 0.5),
        source_chat_id=str(meta.get("source_chat_id", "")) or None,
        access_count=_safe_int(meta.get("access_count", 0)),
        last_accessed_at=_last_accessed_from_metadata(meta),
        user_rating=_safe_float(meta.get("user_rating", 0.5), 0.5),
        pinned=bool(meta.get("pinned", False)),
        status=_status_from_metadata(meta),
        expected_valid_days=evd,
        metadata=extra,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        stored_at=stored_at_from_metadata(meta),
        language="zh" if meta.get("language") == "zh" else "en",
        merge_count=_safe_int(meta.get("merge_count", 0)),
        merge_history=str(meta.get("merge_history", "")),
        scope=_scope_from_metadata(meta),
        lifecycle=_lifecycle_from_metadata(meta),
        summary_l0=str(meta.get("summary_l0", "")),
        overview_l1=str(meta.get("overview_l1", "")),
        domain=_parse_domain(meta.get("domain")),
        domain_category=str(meta.get("domain_category", "")),
        related_entities=_string_list_from_metadata(meta, "related_entities"),
        source_chat_ids=_string_list_from_metadata(meta, "source_chat_ids"),
    )


def semantic_to_doc(m: SemanticMemory) -> VectorDocument:
    """Convert SemanticMemory to VectorDocument."""
    payload: dict[str, str | int | float | bool | list[str]] = {
        "user_id": m.user_id,
        "memory_type": MemoryType.SEMANTIC.value,
        "importance": m.importance,
        "confidence": m.confidence,
        "source_chat_id": m.source_chat_id or "",
        "source_chat_ids": list(m.source_chat_ids),
        "preference_type": m.preference_type or "",
        "preference_strength": m.preference_strength,
        "correction_of": m.correction_of or "",
        "source_error": m.source_error or "",
        "access_count": m.access_count,
        "user_rating": m.user_rating,
        "tags": [t.lower() for t in m.tags],
        "language": m.language,
        "merge_count": m.merge_count,
        "merge_history": m.merge_history,
        "pinned": m.pinned,
        "is_exact_fact": m.is_exact_fact,
        "exact_identifiers": list(m.exact_identifiers),
        "status": m.status,
        "archived": m.status == "archived",
        "expected_valid_days": m.expected_valid_days if m.expected_valid_days is not None else 0,
        "created_at": m.created_at.isoformat(),
        "updated_at": m.updated_at.isoformat(),
        "summary_l0": m.summary_l0,
        "overview_l1": m.overview_l1,
        "domain": m.domain.value if hasattr(m.domain, "value") else str(m.domain),
        "domain_category": m.domain_category,
        **_scope_payload(m.scope),
        **_lifecycle_payload(m.lifecycle),
        **_last_accessed_payload(m.last_accessed_at),
        **stored_ts_payload(m.stored_at),
    }
    for k, v in m.metadata.items():
        if k not in payload:
            payload[k] = v
    return VectorDocument(
        id=m.id,
        content=m.content,
        vector=m.embedding,
        metadata=payload,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def episodic_to_doc(m: EpisodicMemory) -> VectorDocument:
    """Convert EpisodicMemory to VectorDocument."""
    payload: dict[str, str | int | float | bool | list[str]] = {
        "user_id": m.user_id,
        "memory_type": MemoryType.EPISODIC.value,
        "event_type": m.event_type,
        "importance": m.importance,
        "source_chat_id": m.source_chat_id or "",
        "source_chat_ids": list(m.source_chat_ids),
        "related_entities": list(m.related_entities),
        "access_count": m.access_count,
        "user_rating": m.user_rating,
        "tags": [t.lower() for t in getattr(m, "tags", [])],
        "language": m.language,
        "merge_count": m.merge_count,
        "merge_history": m.merge_history,
        "pinned": m.pinned,
        "status": m.status,
        "archived": m.status == "archived",
        "expected_valid_days": m.expected_valid_days if m.expected_valid_days is not None else 0,
        "created_at": m.created_at.isoformat(),
        "updated_at": m.updated_at.isoformat(),
        "summary_l0": m.summary_l0,
        "overview_l1": m.overview_l1,
        "domain": m.domain.value if hasattr(m.domain, "value") else str(m.domain),
        "domain_category": m.domain_category,
        **_scope_payload(m.scope),
        **_lifecycle_payload(m.lifecycle),
        **_last_accessed_payload(m.last_accessed_at),
        **stored_ts_payload(m.stored_at),
    }
    for k, v in m.metadata.items():
        if k not in payload:
            payload[k] = v
    return VectorDocument(
        id=m.id,
        content=m.content,
        vector=m.embedding,
        metadata=payload,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )
