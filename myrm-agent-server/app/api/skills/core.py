from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from myrm_agent_harness.toolkits.storage.types import SkillType
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.skills.schemas import (
    SkillFileUpdateRequest,
    SkillFileUpdateResponse,
    SkillListResponse,
    SkillResponse,
    skill_to_response,
)
from app.core.skills.gates.oauth_availability import apply_integration_oauth_availability
from app.core.skills.store.service import skills_service
from app.database.connection import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=SkillListResponse)
async def list_skills(
    type: str | None = None,
    sort_by: str = "name",
    order: str = "asc",
    workspace_root: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> SkillListResponse:
    """List skills filtered by type, sorted by the given field.

    Pass workspace_root to include project-level workspace skills.
    """
    skill_type = None
    if type:
        try:
            skill_type = SkillType(type)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid skill type: {type}") from e

    valid_sort_fields = {"name", "created_at", "updated_at", "token_cost"}
    if sort_by not in valid_sort_fields:
        sort_by = "name"
    if order not in {"asc", "desc"}:
        order = "asc"

    skills = await skills_service.list_skills(
        skill_type=skill_type,
        sort_by=sort_by,
        order=order,
        workspace_root=workspace_root,
    )
    await apply_integration_oauth_availability(skills, db)

    return SkillListResponse(
        skills=[skill_to_response(s) for s in skills],
        total=len(skills),
    )


@router.get("/{skill_id}/files/{filename}")
async def get_skill_file(skill_id: str, filename: str) -> PlainTextResponse:
    """Get skill file content by skill ID and filename."""
    raw_content = await skills_service.get_skill_file(skill_id, filename)
    if raw_content is None:
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")

    text_body: str
    if isinstance(raw_content, bytes):
        text_body = raw_content.decode("utf-8")
    else:
        text_body = raw_content

    return PlainTextResponse(text_body)


@router.put("/{skill_id}/files/{filename}", response_model=SkillFileUpdateResponse)
async def update_skill_file(
    skill_id: str,
    filename: str,
    payload: SkillFileUpdateRequest,
) -> SkillFileUpdateResponse:
    """Update skill file content, run security scanning, and persist immediately."""
    skill = await skills_service.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    if ".." in filename or filename.startswith(("/", "\\")):
        raise HTTPException(status_code=400, detail="Path traversal detected in filename")

    from myrm_agent_harness.backends.skills.scanning.scanner import (
        SkillTrustRecommendation,
        scan_skill_content,
    )

    scan_res = scan_skill_content(payload.content, filename=filename, skill_name=skill.name)
    if scan_res.trust_recommendation == SkillTrustRecommendation.REJECT:
        rejection_reasons = [f"{f.threat_type}: {f.description}" for f in scan_res.findings if f.severity >= 3]
        raise HTTPException(
            status_code=400,
            detail=f"Security scan rejected skill file modification: {'; '.join(rejection_reasons)}",
        )

    try:
        updated = await skills_service.update_skill_file(skill_id, filename, payload.content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if not updated:
        raise HTTPException(status_code=500, detail=f"Failed to write file {filename} for skill {skill_id}")

    if filename == "SKILL.md" and skill.type == SkillType.PREBUILT:
        import re
        import yaml

        match = re.match(r"^---\s*\n(.*?)\n---\s*\n", payload.content, re.DOTALL)
        if match:
            try:
                fm = yaml.safe_load(match.group(1)) or {}
                if isinstance(fm, dict):
                    await skills_service.update_skill(
                        skill_id=skill.id,
                        description=fm.get("description"),
                        version=str(fm.get("version")) if fm.get("version") else None,
                        tags=fm.get("tags") if isinstance(fm.get("tags"), list) else None,
                        category=fm.get("category"),
                    )
            except Exception as e:
                logger.warning("Failed to sync metadata from updated SKILL.md: %s", e)

    return SkillFileUpdateResponse(
        status="ok",
        skill_id=skill_id,
        filename=filename,
        is_clean=scan_res.is_clean,
        trust_recommendation=scan_res.trust_recommendation.value,
        findings_count=len(scan_res.findings),
    )


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(skill_id: str, db: AsyncSession = Depends(get_db)) -> SkillResponse:
    """Get skill details by ID."""
    skill = await skills_service.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    await apply_integration_oauth_availability([skill], db)
    return skill_to_response(skill)


@router.post("/{skill_id}/reveal")
async def reveal_skill(skill_id: str) -> dict[str, str]:
    """Reveal a local skill directory in the system file manager (Finder/Explorer).

    Local mode only. Opens the directory where the skill is stored.
    """
    from pathlib import Path

    from app.api.files.local_actions import _reveal_in_file_manager, _validate_local_mode

    _validate_local_mode()

    skill = await skills_service.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    if not skill.storage_path:
        raise HTTPException(status_code=400, detail="Skill has no local storage path")

    path = Path(skill.storage_path).resolve()
    if not path.exists():
        raise HTTPException(status_code=404, detail="Skill directory does not exist on disk")

    _reveal_in_file_manager(path)
    return {"status": "ok", "path": str(path)}
