"""Skill evolution event publishing for services layer.

[INPUT]
- app.services.event.app_event_bus::AppEvent, AppEventType, get_event_bus (POS: 业务层 SSE 事件总线)

[OUTPUT]
- publish_skill_evolved_event: 发布 SKILL_EVOLVED 前端刷新事件
- publish_skill_capacity_reached_event: 发布 SKILL_CAPACITY_REACHED 技能库已满提示事件

[POS]
技能进化事件发布：services 层 SKILL_EVOLVED / SKILL_CAPACITY_REACHED 事件唯一出口，供 evolution_review 落盘编排、进化触发容量守卫等消费。
"""

from __future__ import annotations

import logging

from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

logger = logging.getLogger(__name__)


def _publish(event_type: AppEventType, data: dict[str, str | int | None]) -> None:
    """Publish to the SSE bus; a failed notification must never break the evolution flow."""
    try:
        get_event_bus().publish(AppEvent(event_type=event_type, data=data))
    except Exception as exc:
        logger.error("Failed to publish %s event: %s", event_type, exc)


def publish_skill_evolved_event(
    *,
    skill_name: str,
    evolution_type: str,
    description: str,
    evolution_id: str | None = None,
) -> None:
    _publish(
        AppEventType.SKILL_EVOLVED,
        {
            "skill_name": skill_name,
            "evolution_type": evolution_type,
            "description": description[:200],
            "evolution_id": evolution_id,
        },
    )


def publish_skill_capacity_reached_event(*, agent_id: str | None, current_count: int, max_count: int) -> None:
    """Tell the user the skill library is full, so new skills stop being learned automatically."""
    _publish(
        AppEventType.SKILL_CAPACITY_REACHED,
        {"agent_id": agent_id, "current_count": current_count, "max_count": max_count},
    )
