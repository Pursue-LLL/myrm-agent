"""Unit tests for Turn1 catalog preview (evaluate-action-space SSOT)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.backends.skills.types import SkillRequires

from app.api.agents.agent_extras import _build_catalog_preview
from app.core.skills.models import Skill
from app.core.storage.types import SkillType


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
        "overflow_count": 0,
        "catalog_tokens": 0,
        "search_mounted": False,
    }


@pytest.mark.asyncio
async def test_build_catalog_preview_inlines_everything_within_the_token_budget(
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
    assert preview["overflow_count"] == 0
    assert preview["catalog_tokens"] > 0
    assert preview["search_mounted"] is False


@pytest.mark.asyncio
async def test_build_catalog_preview_hidden_mounts_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The catalog is token-budgeted: shrink the budget so 25 equally sized entries cannot all fit.
    monkeypatch.setattr(
        "myrm_agent_harness.agent.skills.runtime.catalog_display.L1_CATALOG_MAX_TOKENS",
        200,
    )
    skills = [_skill(f"id-{idx:02d}", f"beta_skill_{idx:02d}") for idx in range(25)]
    mock_get = AsyncMock(return_value=skills)
    monkeypatch.setattr(
        "app.core.skills.store.service.skills_service.get_skills_by_ids",
        mock_get,
    )
    configs = {skill.id: {"is_core": True} for skill in skills}

    preview = await _build_catalog_preview([s.id for s in skills], configs)

    assert preview["hidden_count"] > 0
    assert preview["inline_count"] + preview["hidden_count"] == len(skills)
    assert preview["overflow_count"] == preview["hidden_count"]  # every skill is core, so each hidden one overflowed
    assert preview["search_mounted"] is True


@pytest.mark.asyncio
async def test_build_catalog_preview_peripheral_skills_are_named_not_overflowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    skills = [_skill(f"id-{idx:02d}", f"delta_skill_{idx:02d}") for idx in range(12)]
    monkeypatch.setattr(
        "app.core.skills.store.service.skills_service.get_skills_by_ids",
        AsyncMock(return_value=skills),
    )

    preview = await _build_catalog_preview([s.id for s in skills], {s.id: {"is_core": False} for s in skills})

    assert preview["inline_count"] == 0
    assert preview["hidden_count"] == 12
    assert preview["overflow_count"] == 0
    assert preview["catalog_tokens"] > 0  # the names line is part of the catalog
    assert preview["search_mounted"] is True


@pytest.mark.asyncio
async def test_build_catalog_preview_matches_the_runtime_catalog_for_an_empty_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from myrm_agent_harness.agent.skills.runtime.skill_catalog_delivery import render_bound_skills_catalog
    from myrm_agent_harness.utils.text_utils import get_token_count

    from app.core.skills.runtime_metadata import skill_to_runtime_metadata

    monkeypatch.setattr(
        "myrm_agent_harness.agent.skills.runtime.catalog_display.L1_CATALOG_MAX_TOKENS",
        200,
    )
    skills = [_skill(f"id-{idx:02d}", f"epsilon_skill_{idx:02d}") for idx in range(25)]
    monkeypatch.setattr(
        "app.core.skills.store.service.skills_service.get_skills_by_ids",
        AsyncMock(return_value=skills),
    )

    preview = await _build_catalog_preview([s.id for s in skills], {})

    runtime = render_bound_skills_catalog([skill_to_runtime_metadata(skill) for skill in skills], skill_configs=None)
    assert runtime is not None
    assert preview["catalog_tokens"] == get_token_count(runtime.xml)
    assert preview["hidden_count"] == runtime.hidden_skill_count > 0
    assert preview["inline_count"] > 0  # no config means no peripheral choice: skills fill the budget


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


@pytest.mark.asyncio
async def test_build_catalog_preview_counts_skill_whose_keys_are_saved_in_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keyed = _skill("keyed-id", "keyed_skill")
    keyed.requires = SkillRequires(env=["PREVIEW_PROBE_KEY"])
    keyed.available = False
    monkeypatch.delenv("PREVIEW_PROBE_KEY", raising=False)
    monkeypatch.setattr(
        "app.core.skills.store.service.skills_service.get_skills_by_ids",
        AsyncMock(return_value=[keyed]),
    )
    monkeypatch.setattr(
        "app.core.skills.gates.requirements_availability._load_skill_env_vars",
        AsyncMock(return_value={"keyed-id": {"PREVIEW_PROBE_KEY": "secret"}}),
    )

    preview = await _build_catalog_preview([keyed.id], {keyed.id: {"is_core": True}})

    assert preview["inline_count"] == 1


@pytest.mark.asyncio
async def test_build_catalog_preview_omits_skill_whose_keys_are_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keyless = _skill("keyless-id", "keyless_skill")
    keyless.requires = SkillRequires(env=["PREVIEW_PROBE_KEY"])
    monkeypatch.delenv("PREVIEW_PROBE_KEY", raising=False)
    monkeypatch.setattr(
        "app.core.skills.store.service.skills_service.get_skills_by_ids",
        AsyncMock(return_value=[keyless]),
    )
    monkeypatch.setattr(
        "app.core.skills.gates.requirements_availability._load_skill_env_vars",
        AsyncMock(return_value={}),
    )

    preview = await _build_catalog_preview([keyless.id], {keyless.id: {"is_core": True}})

    assert preview["inline_count"] == 0
