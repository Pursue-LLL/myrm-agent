"""Browser Domain Skills API — CRUD for domain executable skills.

[INPUT]
- myrm_agent_harness.toolkits.browser.domain_skills (POS: DomainSkillStore singleton)

[OUTPUT]
- router: FastAPI APIRouter with domain skill CRUD endpoints

[POS]
REST entry layer for managing browser domain executable skills.
Exposes list/get/delete and semi-automatic distillation (save from agent action).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.browser.domain_skills import (
        DomainSkillManifest,
        DomainSkillStore,
    )

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class DomainToolResponse(BaseModel):
    name: str
    description: str
    callable_name: str
    args: dict[str, dict[str, str]] = Field(default_factory=dict)
    returns_description: str = ""


class DomainSkillResponse(BaseModel):
    id: str
    name: str
    domains: list[str]
    python_tools: dict[str, DomainToolResponse]
    is_builtin: bool = False


class DistillToolInput(BaseModel):
    description: str = ""
    script_content: str = Field(min_length=1)
    callable_name: str = Field(min_length=1)
    args: dict[str, dict[str, str]] = Field(default_factory=dict)
    returns: str = ""


_SAFE_TOOL_NAME = re.compile(r"^[a-z0-9][a-z0-9_]*$")


class DistillSkillRequest(BaseModel):
    """Semi-automatic distillation: save a domain skill from agent-discovered pattern."""

    skill_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    name: str = Field(min_length=1, max_length=128)
    domains: list[str] = Field(min_length=1)
    tools: dict[str, DistillToolInput] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_tool_names(self) -> DistillSkillRequest:
        for key in self.tools:
            if not _SAFE_TOOL_NAME.match(key):
                msg = f"Invalid tool name '{key}': must match [a-z0-9][a-z0-9_]*"
                raise ValueError(msg)
        return self


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

def _get_store() -> DomainSkillStore:
    from myrm_agent_harness.toolkits.browser.domain_skills import (
        get_global_domain_skill_store,
    )

    return get_global_domain_skill_store()


def _manifest_to_response(
    manifest: DomainSkillManifest,
    *,
    builtin: bool = False,
) -> DomainSkillResponse:
    return DomainSkillResponse(
        id=manifest.id,
        name=manifest.name,
        domains=list(manifest.domains),
        python_tools={
            k: DomainToolResponse(
                name=v.name,
                description=v.description,
                callable_name=v.callable_name,
                args=v.args,
                returns_description=v.returns_description,
            )
            for k, v in manifest.python_tools.items()
        },
        is_builtin=builtin,
    )


@router.get("/domain-skills")
async def list_domain_skills() -> list[DomainSkillResponse]:
    """List all loaded domain skills."""
    store = _get_store()
    return [
        _manifest_to_response(m, builtin=store.is_builtin(m.id))
        for m in store.list_skills()
    ]


@router.get("/domain-skills/{skill_id}")
async def get_domain_skill(skill_id: str) -> DomainSkillResponse:
    """Get a single domain skill by ID."""
    store = _get_store()
    manifest = store.get(skill_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Domain skill not found: {skill_id}")
    return _manifest_to_response(manifest, builtin=store.is_builtin(skill_id))


@router.delete("/domain-skills/{skill_id}")
async def delete_domain_skill(skill_id: str) -> dict[str, bool]:
    """Remove a domain skill from the registry."""
    store = _get_store()
    removed = store.delete_skill(skill_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Domain skill not found: {skill_id}")
    return {"deleted": True}


@router.post("/domain-skills/distill", status_code=201)
async def distill_domain_skill(req: DistillSkillRequest) -> DomainSkillResponse:
    """Semi-automatic distillation: save a user-confirmed domain skill.

    The frontend presents the agent's discovered pattern, the user confirms,
    and the skill is persisted to the user data directory.
    """
    import os

    from myrm_agent_harness.toolkits.browser.domain_skills import (
        DomainSkillManifest,
        DomainTool,
        get_global_domain_skill_store,
    )

    store = get_global_domain_skill_store()

    if store.get(req.skill_id) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Domain skill '{req.skill_id}' already exists. Delete first to replace.",
        )

    data_dir = os.environ.get("MYRM_DATA_DIR", "")
    if data_dir:
        user_skills_dir = Path(data_dir) / "domain_skills"
    else:
        user_skills_dir = Path.home() / ".myrm" / "domain_skills"

    skill_dir = user_skills_dir / req.skill_id
    tools_dir = skill_dir / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)

    python_tools: dict[str, DomainTool] = {}
    manifest_tools: dict[str, dict[str, object]] = {}

    for tool_name, tool_input in req.tools.items():
        script_filename = f"{tool_name}.py"
        script_path = tools_dir / script_filename
        script_path.write_text(tool_input.script_content, encoding="utf-8")

        python_tools[tool_name] = DomainTool(
            name=tool_name,
            description=tool_input.description,
            script_path=f"tools/{script_filename}",
            callable_name=tool_input.callable_name,
            args=tool_input.args,
            returns_description=tool_input.returns,
        )
        manifest_tools[tool_name] = {
            "description": tool_input.description,
            "path": f"tools/{script_filename}",
            "callable": tool_input.callable_name,
            "args": tool_input.args,
            "returns": tool_input.returns,
        }

    manifest_json = {
        "id": req.skill_id,
        "name": req.name,
        "domains": req.domains,
        "python_tools": manifest_tools,
    }
    (skill_dir / "manifest.json").write_text(
        json.dumps(manifest_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    manifest = DomainSkillManifest(
        id=req.skill_id,
        name=req.name,
        domains=tuple(req.domains),
        python_tools=python_tools,
    )
    store.add_user_skill(manifest, skill_dir)

    logger.info("Distilled domain skill: %s (%d tools)", req.skill_id, len(python_tools))
    return _manifest_to_response(manifest)
