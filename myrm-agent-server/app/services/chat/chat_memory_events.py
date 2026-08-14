"""Memory influence ledger projection from assistant message extra_data.

[INPUT]
- myrm_agent_harness.toolkits.memory::MemoryInfluenceRef / MemoryOperationKind / MemoryOperationStatus (POS: 记忆操作账本类型)
- services.memory.operation_ledger::MemoryOperationLedgerService (POS: 记忆操作账本写入)
- database.connection::get_session (POS: 独立会话)

[OUTPUT]
- record_memory_influence_event (POS: assistant 消息落库后投影 citedMemoryRefs / memoryRetrievalTraces 到记忆操作账本)

[POS]
记忆影响账本投影层。Assistant 消息携带记忆引用（citedMemoryRefs）与检索
trace（memoryRetrievalTraces），此处将其投影为记忆操作账本事件，作为消息
持久化的有界 best-effort 副作用。
"""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.memory import MemoryInfluenceRef

logger = logging.getLogger(__name__)


async def record_memory_influence_event(
    *,
    chat_id: str,
    message_id: str,
    content: str,
    extra_data: dict[str, object] | None,
) -> None:
    if not extra_data:
        return
    refs = _memory_influence_refs(extra_data)
    traces = _memory_retrieval_traces(extra_data)
    if not refs and not traces:
        return
    try:
        from myrm_agent_harness.toolkits.memory import (
            MemoryOperationKind,
            MemoryOperationStatus,
        )

        from app.database.connection import get_session
        from app.services.memory.operation_ledger import MemoryOperationLedgerService

        async with get_session() as db:
            ledger = MemoryOperationLedgerService(db)
            for trace in traces:
                trace_id = _optional_str(trace.get("id"))
                query_preview = _optional_str(trace.get("query_preview")) or ""
                result_count = _dict_int(trace, "result_count")
                for index, step in enumerate(_trace_steps(trace)):
                    phase = _optional_str(step.get("phase")) or "recall"
                    status_value = _optional_str(step.get("status"))
                    status = MemoryOperationStatus.SUCCESS
                    if status_value == "skipped":
                        status = MemoryOperationStatus.SKIPPED
                    elif status_value == "warning":
                        status = MemoryOperationStatus.WARNING
                    elif status_value == "error":
                        status = MemoryOperationStatus.ERROR
                    output_count = _dict_int(step, "output_count")
                    await ledger.record_event(
                        kind=MemoryOperationKind.RECALL,
                        status=status,
                        summary=str(step.get("summary") or step.get("title") or phase)[:240],
                        source="memory_retrieval_trace",
                        target_kind="chat",
                        target_id=chat_id,
                        correlation_id=message_id,
                        metadata={
                            "message_id": message_id,
                            "chat_id": chat_id,
                            "trace_id": trace_id,
                            "query_preview": query_preview[:180],
                            "step_index": index,
                            "step_phase": phase,
                            "step_title": str(step.get("title") or phase)[:80],
                            "output_count": output_count,
                            "result_count": result_count,
                            "duration_ms": _optional_float(step.get("duration_ms")),
                        },
                    )
            if refs:
                await ledger.record_event(
                    kind=MemoryOperationKind.CITE,
                    status=MemoryOperationStatus.SUCCESS,
                    summary=f"Assistant answer used {len(refs)} recalled memories: {content[:120]}",
                    source="agent_stream",
                    target_kind="chat",
                    target_id=chat_id,
                    correlation_id=message_id,
                    influence_refs=refs,
                    metadata={
                        "message_id": message_id,
                        "chat_id": chat_id,
                        "influence_count": len(refs),
                    },
                )
            await db.commit()
    except Exception as exc:
        logger.warning("Failed to record memory influence event for chat %s: %s", chat_id, exc)


def _memory_influence_refs(extra_data: dict[str, object]) -> list[MemoryInfluenceRef]:
    raw_refs = extra_data.get("citedMemoryRefs")
    if not isinstance(raw_refs, list):
        return []
    refs: list[MemoryInfluenceRef] = []
    for raw_ref in raw_refs:
        if not isinstance(raw_ref, dict):
            continue
        memory_id = raw_ref.get("id")
        memory_type = raw_ref.get("memory_type")
        if not isinstance(memory_id, str) or not isinstance(memory_type, str):
            continue
        raw_namespaces = raw_ref.get("namespaces")
        refs.append(
            MemoryInfluenceRef(
                memory_id=memory_id,
                memory_type=memory_type,
                score=_optional_float(raw_ref.get("score")),
                content_preview=str(raw_ref.get("content") or "")[:220],
                primary_namespace=_optional_str(raw_ref.get("primary_namespace")),
                namespaces=(
                    [str(item) for item in raw_namespaces if isinstance(item, str)] if isinstance(raw_namespaces, list) else []
                ),
                source_chat_id=_optional_str(raw_ref.get("source_chat_id")),
                source_message_id=_optional_str(raw_ref.get("source_message_id")),
                reason="memory_search_tool",
            )
        )
    return refs


def _memory_retrieval_traces(extra_data: dict[str, object]) -> list[dict[str, object]]:
    raw_traces = extra_data.get("memoryRetrievalTraces")
    if not isinstance(raw_traces, list):
        return []
    traces: list[dict[str, object]] = []
    for raw_trace in raw_traces:
        if isinstance(raw_trace, dict):
            traces.append({str(key): value for key, value in raw_trace.items() if isinstance(key, str)})
    return traces


def _trace_steps(trace: dict[str, object]) -> list[dict[str, object]]:
    raw_steps = trace.get("steps")
    if not isinstance(raw_steps, list):
        return []
    steps: list[dict[str, object]] = []
    for raw_step in raw_steps:
        if isinstance(raw_step, dict):
            steps.append({str(key): value for key, value in raw_step.items() if isinstance(key, str)})
    return steps


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _dict_int(value: object, key: str) -> int:
    if not isinstance(value, dict):
        return 0
    raw = value.get(key)
    if isinstance(raw, bool):
        return 0
    if isinstance(raw, int):
        return max(raw, 0)
    if isinstance(raw, float):
        return max(int(raw), 0)
    return 0
