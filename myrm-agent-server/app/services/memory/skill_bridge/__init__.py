# [POS] app/services/memory/skill_bridge/__init__.py
# [INPUT] service.py
# [OUTPUT] ExternalAgentSkillBridgeService, get_external_skill_bridge_service

"""External agent skill bridge service package."""

from app.services.memory.skill_bridge.service import (
    ExternalAgentSkillBridgeService,
    get_external_skill_bridge_service,
)

__all__ = [
    "ExternalAgentSkillBridgeService",
    "get_external_skill_bridge_service",
]
