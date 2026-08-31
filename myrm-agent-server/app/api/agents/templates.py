"""Agent Templates API
Exposes endpoints to list and instantiate pre-configured agent templates (YAML seeds).

Supports both individual and team templates. Team templates atomically create all
member agents plus a leader, with full rollback on failure.

[INPUT]
- app.services.agent.template_utils::ensure_skills_enabled (POS: Pre-flight skill check and enablement)
- app.database.dto::AgentCreate (POS: Agent creation request model)
- app.services.agent.agent_service::AgentService (POS: Agent CRUD service)

[OUTPUT]
- list_templates(): GET endpoint returning available template metadata (with team members/use_cases)
- instantiate_template(): POST endpoint creating agent(s) from a template atomically

[POS]
Agent template catalog and factory. Reads YAML seeds from assets/prebuilt_agents/,
exposes listing and one-click instantiation for both individual and team templates.
"""

import glob
import logging
import os
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.utils.errors import internal_error, not_found_error
from app.core.utils.response_utils import success_response
from app.database.dto import AgentCreate
from app.schemas.responses import StandardSuccessResponse
from app.services.agent.agent_service import AgentService
from app.services.agent.template_utils import (
    PREBUILT_AGENTS_DIR,
    SkillEnablementError,
    resolve_i18n,
)
from app.services.agent.template_utils import (
    ensure_skills_enabled as _ensure_skills_enabled_svc,
)
from app.services.features.product_surface import is_hidden_prebuilt_template

logger = logging.getLogger(__name__)

router = APIRouter()


class TeamMemberBrief(BaseModel):
    role: str
    name: str
    description: str | None = None


class TemplateListItem(BaseModel):
    id: str
    name: str
    description: str | None = None
    avatar_url: str | None = None
    agent_type: str = "individual"
    is_pareto_preset: bool = False
    cost_reduction_ratio: float | None = None
    routing_config: dict[str, Any] | None = None
    moa_overlay: dict[str, Any] | None = None
    members: list[TeamMemberBrief] | None = None
    use_cases: list[str] | None = None


@router.get("/templates", response_model=StandardSuccessResponse)
async def list_templates(request: Request) -> JSONResponse:
    """List available pre-configured agent templates."""
    accept_lang = request.headers.get("Accept-Language", "en")
    templates = []
    try:
        if not os.path.isdir(PREBUILT_AGENTS_DIR):
            logger.warning("Prebuilt agents directory not found: %s", PREBUILT_AGENTS_DIR)
            return success_response(data=[])

        yaml_files = glob.glob(os.path.join(PREBUILT_AGENTS_DIR, "*.yaml"))
        for file_path in yaml_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if not data:
                        continue
                    template_id = os.path.basename(file_path).replace(".yaml", "")
                    if is_hidden_prebuilt_template(template_id):
                        continue

                    name = resolve_i18n(data.get("name"), accept_lang) or template_id
                    description = resolve_i18n(data.get("description"), accept_lang) if data.get("description") else None
                    agent_type = data.get("agent_type", "individual")

                    members: list[TeamMemberBrief] | None = None
                    use_cases: list[str] | None = None

                    if agent_type == "team":
                        raw_members = data.get("members", [])
                        if raw_members:
                            members = [
                                TeamMemberBrief(
                                    role=m.get("role", "member"),
                                    name=resolve_i18n(m.get("name"), accept_lang),
                                    description=resolve_i18n(m.get("description"), accept_lang) if m.get("description") else None,
                                )
                                for m in raw_members
                            ]
                        raw_use_cases = data.get("use_cases", [])
                        if raw_use_cases:
                            use_cases = [resolve_i18n(uc, accept_lang) for uc in raw_use_cases]

                    templates.append(
                        TemplateListItem(
                            id=template_id,
                            name=name,
                            description=description,
                            avatar_url=data.get("avatar_url"),
                            agent_type=agent_type,
                            is_pareto_preset=bool(data.get("is_pareto_preset", False)),
                            cost_reduction_ratio=float(data["cost_reduction_ratio"]) if data.get("cost_reduction_ratio") is not None else None,
                            routing_config=data.get("routing_config"),
                            moa_overlay=data.get("moa_overlay"),
                            members=members,
                            use_cases=use_cases,
                        ).model_dump(exclude_none=True)
                    )
            except Exception as e:
                logger.error("Failed to parse template %s: %s", file_path, e)

        return success_response(data=templates)
    except Exception as e:
        raise internal_error(operation="List templates", exception=e) from e


@router.post("/instantiate-template/{template_id}", response_model=StandardSuccessResponse)
async def instantiate_template(template_id: str, request: Request) -> JSONResponse:
    """Atomically enable required skills and create agent(s) from a template.

    For team templates: creates all member agents first, then the leader with subagent_ids populated.
    On any failure, rolls back all previously created agents.
    """
    file_path = os.path.join(PREBUILT_AGENTS_DIR, f"{template_id}.yaml")
    if not os.path.exists(file_path):
        raise not_found_error("Agent Template")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            raise HTTPException(status_code=400, detail="Empty template")

        agent_type = data.get("agent_type", "individual")

        if agent_type == "team":
            return await _instantiate_team_template(data, template_id, request)
        return await _instantiate_individual_template(data, template_id, request)

    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Instantiate template", exception=e) from e


async def _ensure_skills_enabled(prebuilt_skill_ids: list[str], template_id: str) -> None:
    """Pre-flight check and enable all required skills. Raises HTTPException on failure."""
    try:
        await _ensure_skills_enabled_svc(prebuilt_skill_ids, template_id)
    except SkillEnablementError as e:
        status = 400 if "does not exist" in str(e) else 500
        raise HTTPException(status_code=status, detail=str(e)) from e


async def _instantiate_individual_template(data: dict[str, Any], template_id: str, request: Request) -> JSONResponse:
    """Create a single individual agent from template data."""
    prebuilt_skill_ids = data.pop("prebuilt_skill_ids", [])
    await _ensure_skills_enabled(prebuilt_skill_ids, template_id)

    accept_lang = request.headers.get("Accept-Language", "en")

    if data.get("name"):
        data["name"] = resolve_i18n(data["name"], accept_lang)
    else:
        data["name"] = template_id

    if data.get("description"):
        data["description"] = resolve_i18n(data["description"], accept_lang)

    data["is_built_in"] = False

    if "skill_ids" not in data:
        data["skill_ids"] = []
    for skill_id in prebuilt_skill_ids:
        if skill_id not in data["skill_ids"]:
            data["skill_ids"].append(skill_id)

    # Remove team-specific fields that don't apply to individual
    data.pop("members", None)
    data.pop("use_cases", None)

    # Process routing_config into model_selection if provided in template YAML
    if "routing_config" in data and not data.get("model_selection"):
        rc = data.pop("routing_config")
        light = rc.get("light_model", {})
        reasoning = rc.get("reasoning_model", {})
        data["model_selection"] = {
            "providerId": "auto",
            "model": reasoning.get("model") or light.get("model") or "gpt-4o",
            "routingEnabled": True,
            "lightProviderId": light.get("provider"),
            "lightModel": light.get("model"),
            "reasoningProviderId": reasoning.get("provider"),
            "reasoningModel": reasoning.get("model"),
        }

    # Process moa_overlay into engine_params if provided in template YAML
    if "moa_overlay" in data:
        moa = data.pop("moa_overlay")
        if not data.get("engine_params"):
            data["engine_params"] = {}
        data["engine_params"]["moa_overlay"] = moa

    agent_data = AgentCreate.model_validate(data)

    from app.api.agents._agent_response import _to_agent_response

    agent = await AgentService.create_agent(agent_data)
    fresh_agent = await AgentService.get_agent_by_id(agent.id) or agent
    return success_response(data=_to_agent_response(fresh_agent).model_dump())


async def _instantiate_team_template(data: dict[str, Any], template_id: str, request: Request) -> JSONResponse:
    """Atomically create a team: all members first, then leader with subagent_ids.

    On failure at any step, rolls back all previously created agents.
    """
    accept_lang = request.headers.get("Accept-Language", "en")
    members_spec: list[dict[str, Any]] = data.get("members", [])
    if not members_spec:
        raise HTTPException(status_code=400, detail="Team template must define at least one member")

    # Gather all required skills across leader + members
    all_skill_ids: list[str] = data.get("prebuilt_skill_ids", [])
    for member in members_spec:
        all_skill_ids.extend(member.get("prebuilt_skill_ids", []))
    unique_skill_ids = list(dict.fromkeys(all_skill_ids))
    await _ensure_skills_enabled(unique_skill_ids, template_id)

    created_agent_ids: list[str] = []

    try:
        # Phase 1: Create member agents
        for member in members_spec:
            member_data = _build_member_agent_data(member, accept_lang)
            member_agent = await AgentService.create_agent(member_data)
            created_agent_ids.append(member_agent.id)

        # Phase 2: Create leader with references to all members
        leader_data = _build_leader_agent_data(data, created_agent_ids, accept_lang, template_id)
        leader_agent = await AgentService.create_agent(leader_data)
        fresh_leader = await AgentService.get_agent_by_id(leader_agent.id) or leader_agent

        from app.api.agents._agent_response import _to_agent_response

        response_data = _to_agent_response(fresh_leader).model_dump()
        response_data["team_member_ids"] = created_agent_ids
        return success_response(data=response_data)

    except Exception as e:
        # Atomic rollback: delete all agents created in this transaction
        for agent_id in reversed(created_agent_ids):
            try:
                await AgentService.delete_agent(agent_id)
                logger.info("Rollback: deleted agent %s during failed team instantiation", agent_id)
            except Exception as rollback_err:
                logger.error("Rollback failed for agent %s: %s", agent_id, rollback_err)

        if isinstance(e, HTTPException):
            raise
        logger.error("Team creation failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Team creation failed, all changes rolled back",
        ) from e


def _build_member_agent_data(member: dict[str, Any], accept_lang: str) -> AgentCreate:
    """Convert a member spec from YAML into an AgentCreate DTO."""
    member_payload: dict[str, Any] = {
        "name": resolve_i18n(member.get("name"), accept_lang),
        "description": resolve_i18n(member.get("description"), accept_lang) if member.get("description") else None,
        "system_prompt": member.get("system_prompt", ""),
        "agent_type": "individual",
        "is_built_in": False,
        "allow_discovery": False,
        "prompt_mode": member.get("prompt_mode", "full"),
        "personality_style": member.get("personality_style", "professional"),
    }

    # Carry over optional fields
    for field in (
        "mcp_ids",
        "mcp_tool_selections",
        "enabled_builtin_tools",
        "skill_ids",
        "suggestion_prompts",
        "is_pareto_preset",
        "cost_reduction_ratio",
    ):
        if field in member:
            member_payload[field] = member[field]

    # Process model_selection from member if provided
    if "model_selection" in member:
        ms = member["model_selection"]
        member_payload["model_selection"] = {
            "providerId": ms.get("provider", "auto"),
            "model": ms.get("model", "gpt-4o"),
        }

    prebuilt_skill_ids = member.get("prebuilt_skill_ids", [])
    if prebuilt_skill_ids:
        if "skill_ids" not in member_payload:
            member_payload["skill_ids"] = []
        for sid in prebuilt_skill_ids:
            if sid not in member_payload["skill_ids"]:
                member_payload["skill_ids"].append(sid)

    return AgentCreate.model_validate(member_payload)


def _build_leader_agent_data(
    data: dict[str, Any],
    member_ids: list[str],
    accept_lang: str,
    template_id: str,
) -> AgentCreate:
    """Build the leader agent DTO from template data with member references."""
    leader_payload: dict[str, Any] = {
        "name": resolve_i18n(data.get("name"), accept_lang) or template_id,
        "description": resolve_i18n(data.get("description"), accept_lang) if data.get("description") else None,
        "system_prompt": data.get("system_prompt", ""),
        "agent_type": "team",
        "is_built_in": False,
        "subagent_ids": member_ids,
        "allow_discovery": data.get("allow_discovery", True),
        "prompt_mode": data.get("prompt_mode", "full"),
        "personality_style": data.get("personality_style", "professional"),
    }

    # Carry over optional fields from leader config
    for field in (
        "mcp_ids",
        "mcp_tool_selections",
        "enabled_builtin_tools",
        "skill_ids",
        "suggestion_prompts",
        "is_pareto_preset",
        "cost_reduction_ratio",
    ):
        if field in data:
            leader_payload[field] = data[field]

    # Process routing_config into model_selection if provided
    if "routing_config" in data and not leader_payload.get("model_selection"):
        rc = data["routing_config"]
        light = rc.get("light_model", {})
        reasoning = rc.get("reasoning_model", {})
        leader_payload["model_selection"] = {
            "providerId": "auto",
            "model": reasoning.get("model") or light.get("model") or "gpt-4o",
            "routingEnabled": True,
            "lightProviderId": light.get("provider"),
            "lightModel": light.get("model"),
            "reasoningProviderId": reasoning.get("provider"),
            "reasoningModel": reasoning.get("model"),
        }

    # Process moa_overlay into engine_params if provided
    if "moa_overlay" in data:
        if not leader_payload.get("engine_params"):
            leader_payload["engine_params"] = {}
        leader_payload["engine_params"]["moa_overlay"] = data["moa_overlay"]

    prebuilt_skill_ids = data.get("prebuilt_skill_ids", [])
    if prebuilt_skill_ids:
        if "skill_ids" not in leader_payload:
            leader_payload["skill_ids"] = []
        for sid in prebuilt_skill_ids:
            if sid not in leader_payload["skill_ids"]:
                leader_payload["skill_ids"].append(sid)

    # Remove team-specific fields that shouldn't go into AgentCreate
    leader_payload.pop("members", None)
    leader_payload.pop("use_cases", None)

    return AgentCreate.model_validate(leader_payload)
