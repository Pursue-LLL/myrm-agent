"""Domain service managing session delta lifecycle and preview injection.

[POS]
app/services/memory/ephemeral_delta_service.py

[INPUT]
- Harness toolkits.memory.ephemeral_delta (SSOT store + tail injector)

[OUTPUT]
- Domain service managing session delta lifecycle and preview injection
"""

from __future__ import annotations

import hashlib
import threading
from datetime import UTC, datetime
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from myrm_agent_harness.toolkits.memory.ephemeral_delta import (
    DeltaActionKind,
    EphemeralDeltaItem,
    HumanTailDeltaInjector,
    get_shared_ephemeral_delta_store,
)

from app.schemas.ephemeral_delta import (
    EphemeralDeltaItemDTO,
    PreviewDeltaInjectionRequestDTO,
    PreviewDeltaInjectionResponseDTO,
    PromptCacheMetricsDTO,
    RecordDeltaRequestDTO,
    SessionDeltaSnapshotDTO,
)


def _action_kind(action: str) -> DeltaActionKind:
    normalized = (action or "").strip().lower()
    if normalized == "retract":
        return DeltaActionKind.RETRACT
    if normalized in {"add_fact", "add"}:
        return DeltaActionKind.ADD_FACT
    return DeltaActionKind.OVERRIDE


def _item_to_dto(session_id: str, item: EphemeralDeltaItem) -> EphemeralDeltaItemDTO:
    return EphemeralDeltaItemDTO(
        delta_id=item.delta_id,
        session_id=session_id,
        target_key=item.target_key,
        content=item.content,
        action=item.action.value,
        turn_index=item.turn_index,
        source=item.source,
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
            action=_action_kind(payload.action),
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

    def preview_injection(
        self, payload: PreviewDeltaInjectionRequestDTO
    ) -> PreviewDeltaInjectionResponseDTO:
        messages = [SystemMessage(content=payload.raw_system_prompt)]
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
