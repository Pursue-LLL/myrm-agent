"""Replay overlay, replay event trail and phase waterfall for the memory command center.

[INPUT]
app.schemas.memory.command_center::MemoryCommand* replay / waterfall / influence / timeline schemas (POS: 记忆指挥中心 API Schema 层)
app.services.memory.command_center.command_center_projection_utils::WATERFALL_PHASES, event_phase, waterfall_* (POS: 指挥中心阶段映射)

[OUTPUT]
build_replay: per-chat replay overlays combining cited-memory influence and ledger events.
build_replay_events: ordered replay event trail from the timeline.
build_waterfall: ten-phase memory pipeline coverage built from timeline events, influence refs and injected token cost.

[POS]
个人大脑指挥中心的会话回放与流水线瀑布投影。均为无状态纯函数，只依赖已构建好的时间线、影响证据与成本画像。
"""

from __future__ import annotations

from datetime import datetime

from app.schemas.memory.command_center import (
    MemoryCommandCostProfile,
    MemoryCommandInfluenceItem,
    MemoryCommandReplayEvent,
    MemoryCommandReplayOverlay,
    MemoryCommandTimelineEvent,
    MemoryCommandWaterfallStep,
)
from app.services.memory.command_center.command_center_projection_utils import (
    WATERFALL_PHASES,
    WaterfallPhase,
    event_phase,
    waterfall_description,
    waterfall_phase,
    waterfall_status,
)

_OVERLAY_LIMIT = 8
_REPLAY_EVENT_LIMIT = 24


def build_replay(
    timeline: list[MemoryCommandTimelineEvent],
    influence: list[MemoryCommandInfluenceItem],
) -> list[MemoryCommandReplayOverlay]:
    overlays: dict[str, MemoryCommandReplayOverlay] = {}
    for item in influence:
        if not item.chat_id:
            continue
        overlays[item.chat_id] = MemoryCommandReplayOverlay(
            chat_id=item.chat_id,
            message_id=item.message_id,
            event_count=1,
            influence_count=len(item.influence_refs),
            last_event_at=item.occurred_at,
            last_summary=item.answer_preview,
        )
    for event in timeline:
        if event.target_kind != "chat" or not event.target_id:
            continue
        current = overlays.get(event.target_id)
        if current is None:
            overlays[event.target_id] = MemoryCommandReplayOverlay(
                chat_id=event.target_id,
                message_id=None,
                event_count=1,
                influence_count=event.influence_count,
                last_event_at=event.occurred_at,
                last_summary=event.description,
            )
            continue
        overlays[event.target_id] = current.model_copy(
            update={
                "event_count": current.event_count + 1,
                "influence_count": current.influence_count + event.influence_count,
                "last_event_at": max(current.last_event_at, event.occurred_at),
            }
        )
    return sorted(overlays.values(), key=lambda item: item.last_event_at, reverse=True)[:_OVERLAY_LIMIT]


def build_replay_events(timeline: list[MemoryCommandTimelineEvent]) -> list[MemoryCommandReplayEvent]:
    return [
        MemoryCommandReplayEvent(
            id=event.id,
            phase=event_phase(event.kind),
            status=event.status,
            occurred_at=event.occurred_at,
            title=event.title,
            summary=event.description,
            target_kind=event.target_kind,
            target_id=event.target_id,
            influence_count=event.influence_count,
        )
        for event in timeline[:_REPLAY_EVENT_LIMIT]
    ]


def build_waterfall(
    timeline: list[MemoryCommandTimelineEvent],
    influence: list[MemoryCommandInfluenceItem],
    cost: MemoryCommandCostProfile,
) -> list[MemoryCommandWaterfallStep]:
    counts: dict[WaterfallPhase, int] = {}
    latest: dict[WaterfallPhase, datetime] = {}
    for event in timeline:
        phase = waterfall_phase(event.kind)
        counts[phase] = counts.get(phase, 0) + 1
        latest[phase] = event.occurred_at
    recall_count = sum(len(item.influence_refs) for item in influence)
    if recall_count:
        counts["recall"] = max(counts.get("recall", 0), recall_count)
        counts["cite"] = max(counts.get("cite", 0), recall_count)
    if cost.estimated_memory_tokens:
        counts["inject"] = max(counts.get("inject", 0), 1)

    return [
        MemoryCommandWaterfallStep(
            phase=phase,
            status=waterfall_status(phase, counts.get(phase, 0)),
            event_count=counts.get(phase, 0),
            evidence_count=recall_count if phase in {"recall", "cite"} else 0,
            latest_at=latest.get(phase),
            description=waterfall_description(phase, counts.get(phase, 0)),
        )
        for phase in WATERFALL_PHASES
    ]
