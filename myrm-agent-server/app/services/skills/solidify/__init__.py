"""Skill solidification service package.

[INPUT]
- app.services.skills.solidify.skill_solidify_service::SkillSolidifyService (POS: Process-local engine of skill solidification: finds the dynamic parameter slots of a deliverable, renders the four-file bundle (SKILL.md, assets/example.html, assets/template.html, references/design_guidelines.md) and keeps bundles and preview pages in in-memory registries; nothing is written to the skill library.)
- app.services.skills.solidify.solidify_types::ExternalPreviewCreateRequest, ExternalPreviewMetadata, ParameterExtractionRule, SkillAssetBundle, SolidifySkillRequest, SolidifySkillResponse (POS: Contract layer of skill solidification: the parameter, request, bundle and response models plus the clean-preview request and metadata models shared by the service and the API router.)

[OUTPUT]
- SkillSolidifyService: the in-memory solidify and clean-preview service
- ExternalPreviewCreateRequest, ExternalPreviewMetadata, ParameterExtractionRule, SkillAssetBundle, SolidifySkillRequest, SolidifySkillResponse: the solidify and external-preview models

[POS]
Package facade of skill solidification: exposes the service and the solidify and external-preview models.
"""

from .skill_solidify_service import SkillSolidifyService
from .solidify_types import (
    ExternalPreviewCreateRequest,
    ExternalPreviewMetadata,
    ParameterExtractionRule,
    SkillAssetBundle,
    SolidifySkillRequest,
    SolidifySkillResponse,
)

__all__ = [
    "ExternalPreviewCreateRequest",
    "ExternalPreviewMetadata",
    "ParameterExtractionRule",
    "SkillAssetBundle",
    "SkillSolidifyService",
    "SolidifySkillRequest",
    "SolidifySkillResponse",
]
