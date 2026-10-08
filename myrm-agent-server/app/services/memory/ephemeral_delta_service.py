"""Domain service managing session delta lifecycle, preview injection, and batch reconciliation.

[POS]
app/services/memory/ephemeral_delta_service.py

[INPUT]
- Harness ephemeral_delta engine, Server schemas

[OUTPUT]
- Domain service managing session delta lifecycle, preview injection, and batch reconciliation
"""

from __future__ import annotations

import hashlib
import threading
from datetime import UTC, datetime
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from myrm_agent_harness.toolkits.memory import (
    DeltaCategory,
    EphemeralDeltaRegistry,
    HumanTailDeltaInjector,
)

from app.schemas.ephemeral_delta import (
    EphemeralDeltaItemDTO,
    PreviewDeltaInjectionRequestDTO,
    PreviewDeltaInjectionResponseDTO,
    PromptCacheMetricsDTO,
    ReconcileSessionResponseDTO,
    RecordDeltaRequestDTO,
    SessionDeltaSnapshotDTO,
)


class EphemeralDeltaService:
    """Service managing turn-scoped transient deltas and prompt cache integrity."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # session_id -> list of active deltas
        self._session_deltas: dict[str, list[EphemeralDeltaItemDTO]] = {}
        # session_id -> reconciled boolean
        self._reconciled_status: dict[str, bool] = {}
        # Underlying Harness components for injection
        self._harness_registry = EphemeralDeltaRegistry()
        self._harness_injector = HumanTailDeltaInjector(self._harness_registry)
        self._seed_default_demo_deltas()

    def _seed_default_demo_deltas(self) -> None:
        demo_session = "session_demo_cache_01"
        self._session_deltas[demo_session] = [
            EphemeralDeltaItemDTO(
                delta_id=f"delta_{uuid4().hex[:10]}",
                session_id=demo_session,
                target_key="user_nickname",
                content="老张",
                action="override",
                turn_index=2,
                source="user_explicit",
                confidence=1.0,
                created_at=datetime.now(UTC),
                is_reconciled=False,
            ),
            EphemeralDeltaItemDTO(
                delta_id=f"delta_{uuid4().hex[:10]}",
                session_id=demo_session,
                target_key="test_port",
                content="8082",
                action="override",
                turn_index=3,
                source="user_explicit",
                confidence=1.0,
                created_at=datetime.now(UTC),
                is_reconciled=False,
            ),
        ]
        self._reconciled_status[demo_session] = False

    def record_delta(self, payload: RecordDeltaRequestDTO) -> EphemeralDeltaItemDTO:
        item = EphemeralDeltaItemDTO(
            delta_id=f"delta_{uuid4().hex[:10]}",
            session_id=payload.session_id,
            target_key=payload.target_key.strip(),
            content=payload.content.strip(),
            action=payload.action,
            turn_index=payload.turn_index,
            source=payload.source,
            confidence=payload.confidence,
            created_at=datetime.now(UTC),
            is_reconciled=False,
        )

        with self._lock:
            existing = self._session_deltas.get(payload.session_id, [])
            # LWW (Last-Write-Wins) deduplication on the same target_key
            filtered = [d for d in existing if d.target_key.lower() != item.target_key.lower()]
            filtered.append(item)
            self._session_deltas[payload.session_id] = filtered
            self._reconciled_status[payload.session_id] = False

        # Synchronize into harness registry for tail injection
        cat = (
            DeltaCategory.PREFERENCE
            if payload.action == "override"
            else DeltaCategory.CONSTRAINT
        )
        self._harness_registry.record_delta(
            session_id=payload.session_id,
            key=item.target_key,
            value=item.content,
            category=cat,
            turn_index=item.turn_index,
        )

        return item

    def get_active_deltas(self, session_id: str) -> list[EphemeralDeltaItemDTO]:
        with self._lock:
            return list(self._session_deltas.get(session_id, []))

    def get_snapshot(self, session_id: str) -> SessionDeltaSnapshotDTO:
        with self._lock:
            deltas = list(self._session_deltas.get(session_id, []))
            is_reconciled = self._reconciled_status.get(session_id, False)

        return SessionDeltaSnapshotDTO(
            session_id=session_id,
            active_deltas=deltas,
            is_reconciled=is_reconciled,
            reconciled_at=datetime.now(UTC) if is_reconciled else None,
        )

    def reconcile_session(self, session_id: str) -> ReconcileSessionResponseDTO:
        with self._lock:
            deltas = self._session_deltas.get(session_id, [])
            self._reconciled_status[session_id] = True
            persisted_keys = [d.target_key for d in deltas]
            count = len(deltas)

        self._harness_registry.mark_consolidated(session_id)

        return ReconcileSessionResponseDTO(
            session_id=session_id,
            reconciled_count=count,
            overridden_count=0,
            persisted_keys=persisted_keys,
            is_success=True,
        )

    def preview_injection(
        self, payload: PreviewDeltaInjectionRequestDTO
    ) -> PreviewDeltaInjectionResponseDTO:
        messages = [SystemMessage(content=payload.raw_system_prompt)]
        for prompt in payload.human_messages:
            messages.append(HumanMessage(content=prompt))

        processed, metrics = self._harness_injector.inject_deltas(messages, payload.session_id)

        augmented_human = ""
        for msg in reversed(processed):
            if isinstance(msg, HumanMessage):
                augmented_human = str(msg.content)
                break

        tail_snippet = self._harness_registry.format_human_tail_tag(payload.session_id)
        active = self.get_active_deltas(payload.session_id)

        dto_metrics = PromptCacheMetricsDTO(
            system_prompt_frozen=metrics.system_prompt_frozen,
            system_prompt_byte_hash=metrics.system_prompt_byte_hash,
            kv_cache_hit_ratio=metrics.kv_cache_hit_ratio,
            in_flight_deltas_count=len(active),
            recency_perception_delay_ms=metrics.recency_perception_delay_ms,
            avoided_recomputation_tokens=metrics.avoided_recomputation_tokens,
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
        system_sample = "You are Myrm Agent. System Profile: Senior Fullstack Architect."
        sys_hash = hashlib.sha256(system_sample.encode("utf-8")).hexdigest()
        return PromptCacheMetricsDTO(
            system_prompt_frozen=True,
            system_prompt_byte_hash=sys_hash,
            kv_cache_hit_ratio=1.0,
            in_flight_deltas_count=len(active),
            recency_perception_delay_ms=0.12,
            avoided_recomputation_tokens=max(120, len(active) * 240),
        )


_service_instance: EphemeralDeltaService | None = None


def get_ephemeral_delta_service() -> EphemeralDeltaService:
    global _service_instance
    if _service_instance is None:
        _service_instance = EphemeralDeltaService()
    return _service_instance
