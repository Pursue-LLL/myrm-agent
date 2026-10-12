"""API router for Agent Skill Engineering Governance and Privilege Verification.

[INPUT]
- ParseSkillContractRequest, DiffSkillContractsRequest, ValidateSkillMountingRequest

[OUTPUT]
- JSON endpoints for skill contract parsing, drift & privilege diffing, and runtime mounting validation.

[POS]
- Server routing layer under `/api/security/skill-governance`.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.schemas.skill_governance import (
    DiffSkillContractsRequest,
    ParseSkillContractRequest,
    SkillDriftAnalysisDto,
    SkillPermissionContractDto,
    ValidateSkillMountingRequest,
    ValidateSkillMountingResponse,
)
from app.services.security.skill_governance_service import get_skill_governance_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/skill-governance", tags=["security-skill-governance"])


@router.post(
    "/parse-contract",
    response_model=SkillPermissionContractDto,
    summary="Parse raw SKILL.md into a formal permission contract",
)
def parse_contract(request: ParseSkillContractRequest) -> SkillPermissionContractDto:
    """Parse Markdown/frontmatter to extract tool requirements, egress, and filesystem bounds."""
    service = get_skill_governance_service()
    return service.parse_contract(request)


@router.post(
    "/diff-contracts",
    response_model=SkillDriftAnalysisDto,
    summary="Diff baseline and target skill versions to detect privilege escalation",
)
def diff_contracts(request: DiffSkillContractsRequest) -> SkillDriftAnalysisDto:
    """Evaluate contract drift, identifying added high-risk tools or elevated permissions."""
    service = get_skill_governance_service()
    return service.diff_contracts(request)


@router.post(
    "/validate-mounting",
    response_model=ValidateSkillMountingResponse,
    summary="Validate whether a skill may be mounted into agent runtime",
)
def validate_mounting(request: ValidateSkillMountingRequest) -> ValidateSkillMountingResponse:
    """Check if skill requires human administrator approval before permitting runtime execution."""
    service = get_skill_governance_service()
    return service.validate_mounting(request)
