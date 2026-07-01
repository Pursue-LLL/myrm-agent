"""Prebuilt skills management endpoints.

[INPUT]
- app.core.skills.store.service::skills_service (POS: skill CRUD service)
- app.core.skills.models::Skill (POS: skill data model)
- app.core.skills.prebuilt_sync::SEEDS_DIR (POS: bundled seeds directory)
- myrm_agent_harness.api.skills::compute_content_hash (POS: SHA-256 content hashing)
- myrm_agent_harness.api.skills::parse_skill_frontmatter (POS: SKILL.md frontmatter parser)

[OUTPUT]
- create_prebuilt_skill: admin upload endpoint
- reset_prebuilt_to_default: restore bundled source for a prebuilt skill
- accept_prebuilt_upstream: accept upstream update for a user-modified skill

[POS]
Prebuilt skill admin and update management API. Includes three-way hash
update control: reset-to-default restores bundled source; accept-upstream
applies pending upstream update and clears has_upstream_update flag.
"""

import json
import logging
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from myrm_agent_harness.agent.skills.discovery.sanitizer import SKILL_MD_FILE
from myrm_agent_harness.api.skills import (
    SkillMetadataError,
    compute_content_hash,
    parse_skill_frontmatter,
)
from myrm_agent_harness.toolkits.storage.paths import (
    get_skill_file_path,
    get_skill_metadata_path,
)
from myrm_agent_harness.toolkits.storage.types import SkillType

from app.api.skills.schemas import SkillResponse, skill_to_response
from app.core.skills.models import Skill
from app.core.skills.prebuilt_sync import SEEDS_DIR
from app.core.skills.store.service import skills_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/admin/prebuilt", response_model=SkillResponse)
async def create_prebuilt_skill(
    name: Annotated[str, Form()],
    description: Annotated[str, Form()],
    category: Annotated[str | None, Form()] = None,
    tags: Annotated[str | None, Form()] = None,
    files: list[UploadFile] = File(...),
) -> SkillResponse:
    """Upload prebuilt skill (admin only)."""
    tag_list = [t.strip() for t in tags.split(",")] if tags else []

    file_contents: dict[str, bytes] = {}
    for f in files:
        if f.filename:
            content = await f.read()
            file_contents[f.filename] = content

    try:
        skill = await skills_service.create_skill(
            name=name,
            description=description,
            skill_type=SkillType.PREBUILT,
            files=file_contents,
            category=category,
            tags=tag_list,
        )
        return skill_to_response(skill)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _find_seed_content(skill_id: str) -> str | None:
    """Read the bundled SKILL.md source for a given prebuilt skill ID."""
    if not SEEDS_DIR.is_dir():
        return None
    for skill_dir in SEEDS_DIR.iterdir():
        if not skill_dir.is_dir() or skill_dir.name.startswith(("_", ".")):
            continue
        skill_md_path = skill_dir / SKILL_MD_FILE
        if not skill_md_path.is_file():
            continue
        content = skill_md_path.read_text(encoding="utf-8")
        try:
            fm = parse_skill_frontmatter(content, skill_dir.name)
        except SkillMetadataError:
            continue
        if (fm.name or skill_dir.name) == skill_id:
            return content
    return None


async def _apply_bundled_source(skill: Skill, skill_id: str) -> None:
    """Overwrite stored skill with bundled source and update origin_hash."""
    source_content = _find_seed_content(skill_id)
    if source_content is None:
        raise HTTPException(status_code=404, detail=f"Bundled source not found for: {skill_id}")

    storage = skills_service.storage
    skill_md_path = get_skill_file_path(SkillType.PREBUILT, skill_id, SKILL_MD_FILE)
    metadata_path = get_skill_metadata_path(SkillType.PREBUILT, skill_id)

    skill.origin_hash = compute_content_hash(source_content)
    skill.has_upstream_update = False

    await storage.write_text(skill_md_path, source_content)
    await storage.write_text(metadata_path, json.dumps(skill.to_dict(), indent=2))


async def _get_prebuilt_skill(skill_id: str) -> Skill:
    """Fetch a prebuilt skill or raise 404."""
    skill = await skills_service.get_skill(skill_id)
    if not skill or skill.type != SkillType.PREBUILT:
        raise HTTPException(status_code=404, detail=f"Prebuilt skill not found: {skill_id}")
    return skill


@router.post("/{skill_id}/reset-to-default")
async def reset_prebuilt_to_default(skill_id: str) -> dict[str, str]:
    """Restore a prebuilt skill to its bundled default source."""
    skill = await _get_prebuilt_skill(skill_id)
    await _apply_bundled_source(skill, skill_id)
    logger.info("Reset prebuilt skill to default: %s", skill_id)
    return {"status": "ok", "message": f"Skill '{skill_id}' restored to bundled default."}


@router.post("/{skill_id}/accept-upstream")
async def accept_prebuilt_upstream(skill_id: str) -> dict[str, str]:
    """Accept pending upstream update for a user-modified prebuilt skill."""
    skill = await _get_prebuilt_skill(skill_id)
    if not skill.has_upstream_update:
        raise HTTPException(status_code=400, detail=f"No upstream update pending for: {skill_id}")
    await _apply_bundled_source(skill, skill_id)
    logger.info("Accepted upstream update for prebuilt skill: %s", skill_id)
    return {"status": "ok", "message": f"Upstream update applied for skill '{skill_id}'."}
