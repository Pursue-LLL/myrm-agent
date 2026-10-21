"""Skill evolution event publishing for services layer.

[INPUT]
- app.services.event.app_event_bus::AppEvent, AppEventType, get_event_bus (POS: 业务层 SSE 事件总线)

[OUTPUT]
- publish_skill_evolved_event: 发布 SKILL_EVOLVED 前端刷新事件（notify=False 时前端只刷新、不弹 toast）

[POS]
技能进化事件发布：services 层 SKILL_EVOLVED 事件唯一出口，供 evolution_review 落盘编排与自动物化消费。
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
    notify: bool = True,
) -> None:
    """Publish ``SKILL_EVOLVED``; ``notify=False`` asks the UI to refresh without a toast.

    Auto-applied growth already announces itself through ``SKILL_GROWTH_UPDATED``, so a second toast would duplicate it.
    """
    _publish(
        AppEventType.SKILL_EVOLVED,
        {
            "skill_name": skill_name,
            "evolution_type": evolution_type,
            "description": description[:200],
            "evolution_id": evolution_id,
            "notify": notify,
        },
    )
