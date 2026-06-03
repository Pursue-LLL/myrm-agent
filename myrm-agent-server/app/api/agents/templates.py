"""Agent Templates API
Exposes endpoints to list and instantiate pre-configured agent templates (YAML seeds).
"""
import glob
import logging
import os
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.skills.store.service import skills_service
from app.core.utils.errors import internal_error, not_found_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.dto import AgentCreate
from app.database.standard_responses import StandardSuccessResponse
from app.services.agent.agent_service import AgentService

logger = logging.getLogger(__name__)

router = APIRouter()

_PREBUILT_AGENTS_ROOT = Path(__file__).resolve().parents[3]
PREBUILT_AGENTS_DIR = str(_PREBUILT_AGENTS_ROOT / "assets" / "prebuilt_agents")


class TemplateListItem(BaseModel):
    id: str
    name: str
    description: str | None = None
    avatar_url: str | None = None
    agent_type: str = "individual"


def resolve_i18n(value: Any, accept_language: str | None) -> str:
    """Resolve a multi-language dictionary to a single string based on Accept-Language.
    If value is a string, returns it directly.
    """
    if not isinstance(value, dict):
        return str(value) if value is not None else ""
    
    # Simple content negotiation
    lang = "en"
    if accept_language:
        # Very basic parsing, e.g. "zh-CN,zh;q=0.9" -> "zh"
        if "zh" in accept_language.lower():
            lang = "zh"
            
    # Try exact match, then general prefix, then first available
    if lang in value:
        return value[lang]
        
    for k in value:
        if k.startswith(lang):
            return value[k]
            
    # Fallback to English if available
    if "en" in value:
        return value["en"]
        
    # Ultimate fallback to the first key
    return str(next(iter(value.values()))) if value else ""


@router.get("/templates", response_model=StandardSuccessResponse)
async def list_templates(request: Request) -> JSONResponse:
    """List available pre-configured agent templates."""
    accept_lang = request.headers.get("Accept-Language", "en")
    templates = []
    try:
        yaml_files = glob.glob(os.path.join(PREBUILT_AGENTS_DIR, "*.yaml"))
        for file_path in yaml_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if not data:
                        continue
                    template_id = os.path.basename(file_path).replace(".yaml", "")
                    
                    name = resolve_i18n(data.get("name"), accept_lang) or template_id
                    description = resolve_i18n(data.get("description"), accept_lang) if data.get("description") else None
                    
                    templates.append(
                        TemplateListItem(
                            id=template_id,
                            name=name,
                            description=description,
                            avatar_url=data.get("avatar_url"),
                            agent_type=data.get("agent_type", "individual"),
                        ).model_dump()
                    )
            except Exception as e:
                logger.error(f"Failed to parse template {file_path}: {e}")
                
        return success_response(data=templates)
    except Exception as e:
        raise internal_error(operation="List templates", exception=e) from e


@router.post("/instantiate-template/{template_id}", response_model=StandardSuccessResponse)
async def instantiate_template(
    template_id: str, 
    request: Request,
    db: Any = Depends(get_db)
) -> JSONResponse:
    """Atomically enable required skills and create an agent from a template."""
    file_path = os.path.join(PREBUILT_AGENTS_DIR, f"{template_id}.yaml")
    if not os.path.exists(file_path):
        raise not_found_error("Agent Template")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            raise HTTPException(status_code=400, detail="Empty template")

        # Extract required skills
        prebuilt_skill_ids = data.pop("prebuilt_skill_ids", [])
        
        # 1. Pre-flight check: ensure all required skills exist in the system
        for skill_id in prebuilt_skill_ids:
            skill = await skills_service.get_skill(skill_id)
            if not skill:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Template requires skill '{skill_id}' which does not exist in the system."
                )

        # 2. Fast-Fail: Atomically enable required skills
        for skill_id in prebuilt_skill_ids:
            try:
                await skills_service.user_config.enable_prebuilt_skill(skill_id)
            except Exception as e:
                logger.error(f"Failed to auto-enable skill {skill_id} for template {template_id}: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to enable required skill '{skill_id}'. Agent creation aborted."
                ) from e

        # 3. Create the agent
        accept_lang = request.headers.get("Accept-Language", "en")
        
        # Resolve localized strings
        if data.get("name"):
            data["name"] = resolve_i18n(data["name"], accept_lang)
        else:
            data["name"] = template_id
            
        if data.get("description"):
            data["description"] = resolve_i18n(data["description"], accept_lang)
            
        # We ensure it's not marked as built-in so the user can edit it freely
        data["is_built_in"] = False
        
        # Add required skills to the agent's skill list
        if "skill_ids" not in data:
            data["skill_ids"] = []
        for skill_id in prebuilt_skill_ids:
            if skill_id not in data["skill_ids"]:
                data["skill_ids"].append(skill_id)

        # Convert dict to AgentCreate DTO
        agent_data = AgentCreate.model_validate(data)
        
        # Use AgentService to create
        from app.api.agents.agent import _to_agent_response
        agent = await AgentService.create_agent(agent_data)
        
        return success_response(data=_to_agent_response(agent).model_dump())

    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Instantiate template", exception=e) from e
