"""Skill instances API - CRUD operations for multi-instance skill support.

Provides REST API for managing skill instances (create, list, get, update, delete).
Each instance has its own configuration (env/config overrides) and persistent state.

Example:
    POST /api/skills/github_skill/instances
    {
        "instance_name": "personal",
        "env_overrides": {"GITHUB_TOKEN": "ghp_xxx"},
        "config_overrides": {"api_base_url": "https://api.github.com"}
    }
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.skills.state_manager_instance import get_state_manager

logger = logging.getLogger(__name__)

router = APIRouter()

# JSON-serializable config value type (flat-level: no deep nesting expected)
ConfigValue = str | int | float | bool | None


class InstanceCreateRequest(BaseModel):
    """Request body for creating a new skill instance."""

    instance_name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Instance name (alphanumeric, hyphens, underscores)",
    )
    env_overrides: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variable overrides for this instance",
    )
    config_overrides: dict[str, ConfigValue] = Field(
        default_factory=dict,
        description="Configuration overrides for this instance",
    )


class InstanceUpdateRequest(BaseModel):
    """Request body for updating an existing skill instance."""

    env_overrides: dict[str, str] | None = Field(
        default=None,
        description="New environment variable overrides (replaces existing)",
    )
    config_overrides: dict[str, ConfigValue] | None = Field(
        default=None,
        description="New configuration overrides (replaces existing)",
    )


class InstanceResponse(BaseModel):
    """Response model for skill instance."""

    instance_name: str
    skill_name: str
    created_at: datetime
    updated_at: datetime
    env_overrides: dict[str, str]
    config_overrides: dict[str, ConfigValue]
    state_file: str | None
    config_schema: dict[str, ConfigValue | dict[str, object] | list[object]] | None = None


class InstanceListResponse(BaseModel):
    """Response model for listing skill instances."""

    skill_name: str
    instances: list[str]
    total: int


@router.post("/{skill_name}/instances", response_model=InstanceResponse, status_code=201)
async def create_instance(
    skill_name: str,
    request: InstanceCreateRequest,
) -> InstanceResponse:
    """Create a new skill instance.

    Args:
        skill_name: Skill name (e.g., "github_skill")
        request: Instance creation request body

    Returns:
        Created instance configuration

    Raises:
        HTTPException: If instance already exists or validation fails
    """
    manager = get_state_manager()

    try:
        config = manager.create_instance(
            skill_name=skill_name,
            instance_name=request.instance_name,
            env_overrides=request.env_overrides,
            config_overrides=request.config_overrides,
        )

        return InstanceResponse(
            instance_name=config.instance_name,
            skill_name=config.skill_name,
            created_at=config.created_at,
            updated_at=config.updated_at,
            env_overrides=config.env_overrides,
            config_overrides=config.config_overrides,
            state_file=config.state_file,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{skill_name}/instances", response_model=InstanceListResponse)
async def list_instances(skill_name: str) -> InstanceListResponse:
    """List all instances for a skill.

    Args:
        skill_name: Skill name (e.g., "github_skill")

    Returns:
        List of instance names
    """
    manager = get_state_manager()
    instance_names = manager.list_instances(skill_name)

    return InstanceListResponse(
        skill_name=skill_name,
        instances=instance_names,
        total=len(instance_names),
    )


@router.get("/{skill_name}/instances/{instance_name}", response_model=InstanceResponse)
async def get_instance(skill_name: str, instance_name: str) -> InstanceResponse:
    """Get skill instance configuration.

    Args:
        skill_name: Skill name (e.g., "github_skill")
        instance_name: Instance name (e.g., "personal")

    Returns:
        Instance configuration

    Raises:
        HTTPException: If instance not found
    """
    manager = get_state_manager()
    config = manager.load_instance_config(skill_name, instance_name)

    if config is None:
        raise HTTPException(
            status_code=404,
            detail=f"Instance not found: {skill_name}.{instance_name}",
        )

    return InstanceResponse(
        instance_name=config.instance_name,
        skill_name=config.skill_name,
        created_at=config.created_at,
        updated_at=config.updated_at,
        env_overrides=config.env_overrides,
        config_overrides=config.config_overrides,
        state_file=config.state_file,
    )


@router.put("/{skill_name}/instances/{instance_name}", response_model=InstanceResponse)
async def update_instance(
    skill_name: str,
    instance_name: str,
    request: InstanceUpdateRequest,
) -> InstanceResponse:
    """Update an existing skill instance.

    Args:
        skill_name: Skill name (e.g., "github_skill")
        instance_name: Instance name (e.g., "personal")
        request: Instance update request body

    Returns:
        Updated instance configuration

    Raises:
        HTTPException: If instance not found
    """
    manager = get_state_manager()

    config = manager.update_instance(
        skill_name=skill_name,
        instance_name=instance_name,
        env_overrides=request.env_overrides,
        config_overrides=request.config_overrides,
    )

    if config is None:
        raise HTTPException(
            status_code=404,
            detail=f"Instance not found: {skill_name}.{instance_name}",
        )

    return InstanceResponse(
        instance_name=config.instance_name,
        skill_name=config.skill_name,
        created_at=config.created_at,
        updated_at=config.updated_at,
        env_overrides=config.env_overrides,
        config_overrides=config.config_overrides,
        state_file=config.state_file,
    )


@router.delete("/{skill_name}/instances/{instance_name}", status_code=204)
async def delete_instance(skill_name: str, instance_name: str) -> None:
    """Delete a skill instance and its state.

    Args:
        skill_name: Skill name (e.g., "github_skill")
        instance_name: Instance name (e.g., "personal")

    Raises:
        HTTPException: If instance not found
    """
    manager = get_state_manager()

    deleted = manager.delete_instance(skill_name, instance_name)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Instance not found: {skill_name}.{instance_name}",
        )
