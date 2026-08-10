"""Skill evolution event publishing for services layer.

[INPUT]
- app.services.event.app_event_bus::AppEvent, AppEventType, get_event_bus (POS: 业务层 SSE 事件总线)

[OUTPUT]
- publish_skill_evolved_event: 发布 SKILL_EVOLVED 前端刷新事件

[POS]
技能进化事件发布：services 层 SKILL_EVOLVED 事件唯一出口，供 evolution_review 落盘编排等消费。
"""

from __future__ import annotations

import logging

from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

logger = logging.getLogger(__name__)


def publish_skill_evolved_event(
    *,
    skill_name: str,
    evolution_type: str,
    description: str,
    evolution_id: str | None = None,
) -> None:
    try:
        bus = get_event_bus()
        bus.publish(
            AppEvent(
                event_type=AppEventType.SKILL_EVOLVED,
                data={
                    "skill_name": skill_name,
                    "evolution_type": evolution_type,
                    "description": description[:200],
                    "evolution_id": evolution_id,
                },
            )
        )
    except Exception as exc:
        logger.error("Failed to publish skill evolved event: %s", exc)
