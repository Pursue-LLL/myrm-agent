"""[INPUT] Skill solidification domain models and service.
[OUTPUT] Public exports for skill solidify service and schemas.
[POS] app/services/skills/solidify/__init__.py.
"""

from .solidify_types import (
    ExternalPreviewCreateRequest,
    ExternalPreviewMetadata,
    ParameterExtractionRule,
    SkillAssetBundle,
    SolidifySkillRequest,
    SolidifySkillResponse,
)
from .skill_solidify_service import SkillSolidifyService

__all__ = [
    "ExternalPreviewCreateRequest",
    "ExternalPreviewMetadata",
    "ParameterExtractionRule",
    "SkillAssetBundle",
    "SkillSolidifyService",
    "SolidifySkillRequest",
    "SolidifySkillResponse",
]
