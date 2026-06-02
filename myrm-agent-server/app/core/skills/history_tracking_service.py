"""History tracking skill service — business-layer wrapper with history tracking.

[INPUT]
- creation.service::SkillCreationService (POS: Inner skill creation service)
- myrm_agent_harness.skills.history::HistoryTrackingSkillWriteBackend, JsonlHistoryBackend
  (POS: History components from framework)

[OUTPUT]
- HistoryTrackingSkillService: Wrapper service with automatic history tracking
- history_skill_service: Singleton instance

[POS]
Business-layer wrapper that adapts the framework's HistoryTrackingSkillWriteBackend
to the Server's SkillCreationService and provides default history storage.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TypeAlias

from myrm_agent_harness.agent.skills.history import (
    HistoryTrackingSkillWriteBackend,
    JsonlHistoryBackend,
    SkillHistoryBackend,
    SkillHistoryRecord,
    SkillRollbackResult,
)

logger = logging.getLogger(__name__)

HistoryTrackingSkillService: TypeAlias = HistoryTrackingSkillWriteBackend


def create_history_tracking_skill_service() -> HistoryTrackingSkillService:
    """Create HistoryTrackingSkillService with default history backend.

    By default, uses JsonlHistoryBackend for file-based storage.

    Returns:
        History tracking skill service
    """
    from app.config.settings import settings
    from app.core.skills.creation.service import skill_creation_service
    from app.core.skills.store.service import skills_service

    # Use same parent directory as LOCAL_SKILLS_DIR
    history_root = Path(settings.database.state_dir) / "skill_history"
    history_backend: SkillHistoryBackend = JsonlHistoryBackend(history_root)

    # Note: SkillCreationService implements SkillWriteBackend.
    # skills_service.local_skills acts as a SkillBackend.

    return HistoryTrackingSkillWriteBackend(
        read_backend=skills_service.local_skills,
        write_backend=skill_creation_service,
        history_backend=history_backend,
    )


# Singleton instance
history_skill_service = create_history_tracking_skill_service()

__all__ = [
    "HistoryTrackingSkillService",
    "create_history_tracking_skill_service",
    "history_skill_service",
    "SkillHistoryRecord",
    "SkillRollbackResult",
]
