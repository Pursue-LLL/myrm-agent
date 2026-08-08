"""Unit tests for Turn1 catalog preview (evaluate-action-space SSOT)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.toolkits.storage.types import SkillType

from app.api.agents.agent_extras import _build_catalog_preview
from app.core.skills.models import Skill


def _skill(skill_id: str, name: str) -> Skill:
    return Skill(
        id=skill_id,
        type=SkillType.PREBUILT,
        name=name,
        description=f"{name} description",
        storage_path=f"/tmp/{skill_id}",
    )


@pytest.mark.asyncio
async def test_build_catalog_preview_empty_skill_ids() -> None:
    preview = await _build_catalog_preview([], {})
    assert preview == {
        "inline_count": 0,
        "hidden_count": 0,
        "search_mounted": False,
        "inline_cap": 20,
    }


@pytest.mark.asyncio
async def test_build_catalog_preview_inline_at_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills = [_skill(f"id-{idx:02d}", f"alpha_skill_{idx:02d}") for idx in range(8)]
    mock_get = AsyncMock(return_value=skills)
    monkeypatch.setattr(
        "app.core.skills.store.service.skills_service.get_skills_by_ids",
        mock_get,
    )
    configs = {skill.id: {"is_core": True} for skill in skills}

    preview = await _build_catalog_preview([s.id for s in skills], configs)

    assert preview["inline_count"] == 8
    assert preview["hidden_count"] == 0
    assert preview["search_mounted"] is False
    assert preview["inline_cap"] == 20


@pytest.mark.asyncio
async def test_build_catalog_preview_hidden_mounts_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills = [_skill(f"id-{idx:02d}", f"beta_skill_{idx:02d}") for idx in range(25)]
    mock_get = AsyncMock(return_value=skills)
    monkeypatch.setattr(
        "app.core.skills.store.service.skills_service.get_skills_by_ids",
        mock_get,
    )
    configs = {skill.id: {"is_core": True} for skill in skills}

    preview = await _build_catalog_preview([s.id for s in skills], configs)

    assert preview["inline_count"] == 20
    assert preview["hidden_count"] == 5
    assert preview["search_mounted"] is True


@pytest.mark.asyncio
async def test_build_catalog_preview_skips_invalid_skill_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    valid = _skill("valid-id", "gamma_skill")
    invalid = _skill("invalid-id", "   ")
    mock_get = AsyncMock(return_value=[valid, invalid])
    monkeypatch.setattr(
        "app.core.skills.store.service.skills_service.get_skills_by_ids",
        mock_get,
    )

    preview = await _build_catalog_preview(
        [valid.id, invalid.id],
        {valid.id: {"is_core": True}},
    )

    assert preview["inline_count"] == 1
    assert preview["hidden_count"] == 0
    assert preview["search_mounted"] is False
