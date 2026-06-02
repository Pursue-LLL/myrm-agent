"""Skill evolution event publishing for services layer."""

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
