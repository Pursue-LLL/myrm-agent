"""Domain service of the ephemeral delta API.

[INPUT]
- myrm_agent_harness.toolkits.memory.ephemeral_delta::DeltaActionKind, EphemeralDeltaItem, HumanTailDeltaInjector, get_shared_ephemeral_delta_store (POS: Prompt-cache-preserving ephemeral session delta memory suite.)
- app.schemas.ephemeral_delta::DeltaActionDTO, EphemeralDeltaItemDTO, PreviewDeltaInjectionRequestDTO, PreviewDeltaInjectionResponseDTO, PromptCacheMetricsDTO, RecordDeltaRequestDTO, SessionDeltaSnapshotDTO (POS: Wire contracts of the ephemeral delta API shared by its router and service; `revoke` is the API name of a tombstone delta.)
- app.services.memory.ephemeral_delta_volume::ensure_default_volume_ephemeral_persistence (POS: Persistence binding of the ephemeral delta suite: resolves the Volume's memory database and attaches it to the process-wide delta store for the REST service and the agent paths.)

[OUTPUT]
- EphemeralDeltaService: records, lists and snapshots a session's deltas, previews the tail injection and reports layout metrics
- get_ephemeral_delta_service: process-wide service accessor used as the router dependency

[POS]
Service behind the ephemeral delta API: records session deltas into the process-wide shared store (API `revoke` becomes a
harness tombstone), previews how the active deltas are appended to the last human message under an unchanged system prompt,
and reports layout metrics only (cache hit ratio, delay and saved tokens stay unset).
"""

from __future__ import annotations

import hashlib
import threading
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from myrm_agent_harness.toolkits.memory.ephemeral_delta import (
    DeltaActionKind,
    EphemeralDeltaItem,
    HumanTailDeltaInjector,
    get_shared_ephemeral_delta_store,
)

from app.schemas.ephemeral_delta import (
    DeltaActionDTO,
    DeltaSourceDTO,
    EphemeralDeltaItemDTO,
    PreviewDeltaInjectionRequestDTO,
    PreviewDeltaInjectionResponseDTO,
    PromptCacheMetricsDTO,
    RecordDeltaRequestDTO,
    SessionDeltaSnapshotDTO,
)

# The HTTP contract names a tombstone `revoke` while the harness store calls it RETRACT; both directions are
# mapped here so a revoke suppresses its key and the response DTO stays valid for tombstone items.
_API_ACTION_TO_KIND: dict[DeltaActionDTO, DeltaActionKind] = {
    "override": DeltaActionKind.OVERRIDE,
    "add_fact": DeltaActionKind.ADD_FACT,
    "revoke": DeltaActionKind.RETRACT,
}
_KIND_TO_API_ACTION: dict[DeltaActionKind, DeltaActionDTO] = {kind: name for name, kind in _API_ACTION_TO_KIND.items()}


def _item_to_dto(session_id: str, item: EphemeralDeltaItem) -> EphemeralDeltaItemDTO:
    return EphemeralDeltaItemDTO(
        delta_id=item.delta_id,
        session_id=session_id,
        target_key=item.target_key,
        content=item.content,
        action=_KIND_TO_API_ACTION[item.action],
        turn_index=item.turn_index,
        # The store keeps free-form strings; pydantic still enforces the two values the API allows.
        source=cast(DeltaSourceDTO, item.source),
        confidence=item.confidence,
        created_at=datetime.now(UTC),
        is_reconciled=False,
    )


class EphemeralDeltaService:
    """Service managing turn-scoped transient deltas and prompt cache integrity."""

    def __init__(self) -> None:
        from app.services.memory.ephemeral_delta_volume import (
            ensure_default_volume_ephemeral_persistence,
        )

        ensure_default_volume_ephemeral_persistence()
        self._lock = threading.Lock()
        self._store = get_shared_ephemeral_delta_store()
        self._injector = HumanTailDeltaInjector()

    def record_delta(self, payload: RecordDeltaRequestDTO) -> EphemeralDeltaItemDTO:
        item = EphemeralDeltaItem(
            delta_id=f"delta_{uuid4().hex[:10]}",
            target_key=payload.target_key.strip(),
            content=payload.content.strip(),
            action=_API_ACTION_TO_KIND[payload.action],
            turn_index=payload.turn_index,
            source=payload.source,
            confidence=payload.confidence,
        )
        with self._lock:
            self._store.record_delta(payload.session_id, item)
        return _item_to_dto(payload.session_id, item)

    def get_active_deltas(self, session_id: str) -> list[EphemeralDeltaItemDTO]:
        active = self._store.get_active_deltas(session_id)
        return [_item_to_dto(session_id, item) for item in active]

    def get_snapshot(self, session_id: str) -> SessionDeltaSnapshotDTO:
        snapshot = self._store.get_snapshot(session_id)
        return SessionDeltaSnapshotDTO(
            session_id=session_id,
            active_deltas=[_item_to_dto(session_id, item) for item in snapshot.deltas],
            is_reconciled=snapshot.is_reconciled,
            reconciled_at=datetime.now(UTC) if snapshot.is_reconciled else None,
        )

    def preview_injection(self, payload: PreviewDeltaInjectionRequestDTO) -> PreviewDeltaInjectionResponseDTO:
        messages: list[AnyMessage] = [SystemMessage(content=payload.raw_system_prompt)]
        for prompt in payload.human_messages:
            messages.append(HumanMessage(content=prompt))

        deltas = self._store.get_active_deltas(payload.session_id)
        processed = self._injector.inject_deltas(messages, deltas)

        augmented_human = ""
        for msg in reversed(processed):
            if isinstance(msg, HumanMessage):
                augmented_human = str(msg.content)
                break

        tail_snippet = self._injector.format_deltas_block(deltas)
        active = self.get_active_deltas(payload.session_id)
        sys_hash = hashlib.sha256(payload.raw_system_prompt.encode("utf-8")).hexdigest()

        dto_metrics = PromptCacheMetricsDTO(
            system_prompt_frozen=True,
            system_prompt_byte_hash=sys_hash,
            kv_cache_hit_ratio=None,
            in_flight_deltas_count=len(active),
            recency_perception_delay_ms=None,
            avoided_recomputation_tokens=None,
        )

        return PreviewDeltaInjectionResponseDTO(
            session_id=payload.session_id,
            frozen_system_prompt=payload.raw_system_prompt,
            augmented_final_human_message=augmented_human,
            tail_tag_snippet=tail_snippet,
            active_deltas=active,
            metrics=dto_metrics,
        )

    def get_metrics(self, session_id: str) -> PromptCacheMetricsDTO:
        active = self.get_active_deltas(session_id)
        return PromptCacheMetricsDTO(
            system_prompt_frozen=True,
            system_prompt_byte_hash=None,
            kv_cache_hit_ratio=None,
            in_flight_deltas_count=len(active),
            recency_perception_delay_ms=None,
            avoided_recomputation_tokens=None,
        )


_service_instance: EphemeralDeltaService | None = None


def get_ephemeral_delta_service() -> EphemeralDeltaService:
    global _service_instance
    if _service_instance is None:
        _service_instance = EphemeralDeltaService()
    return _service_instance
