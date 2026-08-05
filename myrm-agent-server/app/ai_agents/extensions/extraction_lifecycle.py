"""Memory extraction lifecycle observer — records write/extract phases to operation ledger + SSE.

[INPUT]
myrm_agent_harness.agent._internals.memory_extraction::ExtractionLifecycleObserver (POS: harness callback protocol)
app.services.memory.operation_ledger::MemoryOperationLedgerService (POS: memory operation ledger)

[OUTPUT]
make_extraction_lifecycle_observer: Factory for harness ExtractionLifecycleObserver callback (optional source + manual_retry metadata).

[POS]
Business-layer bridge from harness post-turn auto_extract_memories to GUI-visible telemetry.
Does not inject prompt content — SSE/UI only.
"""

from __future__ import annotations

import logging
from typing import Literal

from myrm_agent_harness.toolkits.memory import (
    MemoryOperationKind,
    MemoryOperationStatus,
)

logger = logging.getLogger(__name__)

JsonScalar = str | int | float | bool | None


def make_extraction_lifecycle_observer(
    effective_chat_id: str,
    *,
    source: str = "auto_extract_memories",
    manual_retry: bool = False,
):
    """Build observer bound to one chat session for ledger + SSE publish."""

    async def _observe(
        phase: Literal["write", "extract"],
        status: MemoryOperationStatus,
        *,
        chat_id: str | None,
        summary: str,
        metadata: dict[str, JsonScalar] | None = None,
    ) -> None:
        resolved_chat_id = (chat_id or effective_chat_id or "").strip()
        if not resolved_chat_id:
            return

        kind = (
            MemoryOperationKind.WRITE
            if phase == "write"
            else MemoryOperationKind.EXTRACT
        )
        meta: dict[str, JsonScalar] = {"chat_id": resolved_chat_id, "phase": phase}
        if manual_retry:
            meta["manual_retry"] = True
        if metadata:
            for key, value in metadata.items():
                if isinstance(value, (str, int, float, bool)) or value is None:
                    meta[str(key)] = value

        try:
            from app.database.connection import get_session
            from app.services.memory.operation_ledger import (
                MemoryOperationLedgerService,
            )

            async with get_session() as db:
                await MemoryOperationLedgerService(db).record_event(
                    kind=kind,
                    status=status,
                    summary=summary[:240],
                    source=source,
                    target_kind="chat",
                    target_id=resolved_chat_id,
                    metadata=meta,
                    commit=True,
                )

            if (
                phase == "extract"
                and status == MemoryOperationStatus.SUCCESS
                and (
                    (
                        isinstance(meta.get("stored_count"), int)
                        and meta["stored_count"] > 0
                    )
                    or (
                        isinstance(meta.get("verbatim_count"), int)
                        and meta["verbatim_count"] > 0
                    )
                )
            ):
                count = meta.get("stored_count") or meta.get("verbatim_count")
                from app.services.event.app_event_bus import (
                    AppEvent,
                    AppEventType,
                    get_event_bus,
                )

                get_event_bus().publish(
                    AppEvent(
                        event_type=AppEventType.MEMORY_OPERATION,
                        data={
                            "operation": "auto_memory_extracted",
                            "count": count,
                            "source": "session_end",
                            "chat_id": resolved_chat_id,
                        },
                    )
                )
        except Exception as exc:
            logger.warning("Failed to record extraction lifecycle event: %s", exc)

    return _observe


__all__ = ["make_extraction_lifecycle_observer"]
