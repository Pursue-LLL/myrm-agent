"""Security Profile API schemas.

Pydantic models for profile CRUD endpoints.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProfileResponse(BaseModel):
    """Single security profile."""

    id: str
    profile_key: str = Field(..., alias="profileKey")
    display_name: str = Field(..., alias="displayName")
    description: str | None = None
    config_json: dict[str, object] = Field(..., alias="configJson")
    is_builtin: bool = Field(..., alias="isBuiltin")
    is_active: bool = Field(..., alias="isActive")
    created_at: str | None = Field(None, alias="createdAt")
    updated_at: str | None = Field(None, alias="updatedAt")

    class Config:
        populate_by_name = True


class ProfileCreateRequest(BaseModel):
    """Create or update a profile."""

    profile_key: str = Field(..., min_length=1, max_length=100, alias="profileKey")
    display_name: str = Field(..., min_length=1, max_length=255, alias="displayName")
    description: str | None = None
    config_json: dict[str, object] = Field(..., alias="configJson")

    class Config:
        populate_by_name = True


class ProfileCloneRequest(BaseModel):
    """Clone an existing profile."""

    source_key: str = Field(..., alias="sourceKey")
    new_key: str = Field(..., min_length=1, max_length=100, alias="newKey")
    new_display_name: str = Field(..., min_length=1, max_length=255, alias="newDisplayName")

    class Config:
        populate_by_name = True


class ProfileListResponse(BaseModel):
    """List of profiles."""

    profiles: list[ProfileResponse]
    active_key: str | None = Field(None, alias="activeKey")

    class Config:
        populate_by_name = True
