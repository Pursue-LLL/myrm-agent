"""Feature flags API endpoints.

Provides feature status query and experimental feature toggle for the frontend.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.core.features import get_features, init_features, registry
from myrm_agent_harness.core.features.types import FeatureStage
from pydantic import BaseModel

from app.services.features.feature_config_service import (
    load_user_overrides,
    remove_feature_override,
    set_feature_override,
)

router = APIRouter()


class FeatureStatusItem(BaseModel):
    id: str
    key: str
    description: str
    stage: str
    enabled: bool
    default_enabled: bool
    is_overridden: bool
    experimental_name: str | None = None
    experimental_description: str | None = None
    announcement: str | None = None
    deprecation_hint: str | None = None


class FeatureStatusResponse(BaseModel):
    features: list[FeatureStatusItem]
    warnings: list[str]


class ToggleRequest(BaseModel):
    enabled: bool


class ToggleResponse(BaseModel):
    feature_id: str
    enabled: bool
    restarted: bool


@router.get("", response_model=FeatureStatusResponse)
async def get_all_features() -> FeatureStatusResponse:
    """Get status of all features."""
    feature_set = get_features()
    user_overrides = load_user_overrides()
    items: list[FeatureStatusItem] = []

    for spec in registry.all_specs():
        if spec.stage == FeatureStage.REMOVED:
            continue

        exp_name = None
        exp_desc = None
        announcement = None
        if spec.experimental_info:
            exp_name = spec.experimental_info.name
            exp_desc = spec.experimental_info.description
            announcement = spec.experimental_info.announcement or None

        dep_hint = None
        if spec.deprecation_info:
            dep_hint = spec.deprecation_info.migration_hint

        items.append(
            FeatureStatusItem(
                id=spec.id,
                key=spec.key,
                description=spec.description,
                stage=spec.stage.value,
                enabled=feature_set.enabled(spec.id),
                default_enabled=spec.default_enabled,
                is_overridden=spec.id in user_overrides or spec.key in user_overrides,
                experimental_name=exp_name,
                experimental_description=exp_desc,
                announcement=announcement,
                deprecation_hint=dep_hint,
            )
        )

    return FeatureStatusResponse(
        features=items,
        warnings=feature_set.warnings(),
    )


@router.get("/experimental", response_model=FeatureStatusResponse)
async def get_experimental_features() -> FeatureStatusResponse:
    """Get only experimental features (for the settings menu)."""
    feature_set = get_features()
    user_overrides = load_user_overrides()
    items: list[FeatureStatusItem] = []

    for spec in registry.experimental_specs():
        exp_name = None
        exp_desc = None
        announcement = None
        if spec.experimental_info:
            exp_name = spec.experimental_info.name
            exp_desc = spec.experimental_info.description
            announcement = spec.experimental_info.announcement or None

        items.append(
            FeatureStatusItem(
                id=spec.id,
                key=spec.key,
                description=spec.description,
                stage=spec.stage.value,
                enabled=feature_set.enabled(spec.id),
                default_enabled=spec.default_enabled,
                is_overridden=spec.id in user_overrides or spec.key in user_overrides,
                experimental_name=exp_name,
                experimental_description=exp_desc,
                announcement=announcement,
            )
        )

    return FeatureStatusResponse(features=items, warnings=[])


@router.post("/{feature_id}/toggle", response_model=ToggleResponse)
async def toggle_feature(feature_id: str, body: ToggleRequest) -> ToggleResponse:
    """Toggle a feature on/off. Persists the override and re-initializes FeatureSet."""
    spec = registry.get(feature_id)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown feature: {feature_id}")

    if spec.stage == FeatureStage.REMOVED:
        raise HTTPException(
            status_code=400,
            detail=f"Feature '{feature_id}' has been removed from the product surface",
        )

    if spec.stage == FeatureStage.UNDER_DEVELOPMENT:
        raise HTTPException(
            status_code=400,
            detail=f"Feature '{feature_id}' is under development and not available to toggle",
        )

    updated_overrides = set_feature_override(feature_id, body.enabled)
    init_features(overrides=updated_overrides)

    return ToggleResponse(
        feature_id=feature_id,
        enabled=body.enabled,
        restarted=False,
    )


@router.post("/{feature_id}/reset", response_model=ToggleResponse)
async def reset_feature(feature_id: str) -> ToggleResponse:
    """Reset a feature to its default state."""
    spec = registry.get(feature_id)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown feature: {feature_id}")

    updated_overrides = remove_feature_override(feature_id)
    init_features(overrides=updated_overrides)

    return ToggleResponse(
        feature_id=feature_id,
        enabled=spec.default_enabled,
        restarted=False,
    )
