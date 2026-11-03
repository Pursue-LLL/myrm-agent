"""Turn-1 catalog preview: the agent config page shows what the agent runtime delivers.

The preview loads the bound skills through the composition the agent factories build
(`create_skill_backend` + `load_skills`) and renders them with the runtime's resolver and renderer, so a skill
counts once, under the name the model sees, with the availability verdict the runtime gives it. The skills are
the real seeded prebuilt set over a scratch storage; every check that compares numbers feeds the same input
through the runtime path and through `_build_catalog_preview`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from myrm_agent_harness.agent.skills.runtime.skill_catalog_delivery import render_bound_skills_catalog
from myrm_agent_harness.backends.skills.types import SkillMetadata
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend
from myrm_agent_harness.utils.text_utils import get_token_count

from app.api.agents.agent_extras import _build_catalog_preview
from app.core.skills import prebuilt_sync
from app.core.skills.gates.oauth_availability import ALL_INTEGRATION_GATED_SKILL_IDS
from app.core.skills.loader import create_skill_backend
from app.core.skills.providers.local import LocalSkillsProvider
from app.core.skills.store.service import SkillsService
from app.core.storage.types import SkillType

_CATALOG_BUDGET = "myrm_agent_harness.agent.skills.runtime.catalog_display.L1_CATALOG_MAX_TOKENS"
_LOCAL_SKILL_MD = "---\nname: probe-local\ndescription: A local probe skill\n---\n# probe-local\n\nLocal SOP body.\n"

SkillConfigs = dict[str, dict[str, object]]


@pytest.fixture(autouse=True)
def _fresh_prebuilt_sync() -> Iterator[None]:
    prebuilt_sync._synced = False  # noqa: SLF001
    yield
    prebuilt_sync._synced = False  # noqa: SLF001


@pytest_asyncio.fixture
async def service(tmp_path: Path) -> AsyncIterator[SkillsService]:
    """Every seeded prebuilt skill, enabled, over a scratch storage that stands in for the app's skills service."""
    storage = LocalStorageBackend(str(tmp_path / "storage"))
    svc = SkillsService(storage=storage)
    sync_result = await prebuilt_sync.sync_prebuilt_seeds(storage)
    config = await svc.user_config.get_config()
    config.enabled_prebuilt_ids = list(sync_result.skill_ids)
    await svc.user_config.save_config(config)
    with (
        patch("app.core.skills.store.service.skills_service", svc),
        patch("app.core.skills.effective_skill_ids.skills_service", svc),
        # The scan roots of a real install belong to the machine; a test installs only the folders it writes.
        patch("app.core.skills.store.reader.list_local_skills", AsyncMock(return_value=[])),
    ):
        yield svc


@pytest_asyncio.fixture
async def plain_ids(service: SkillsService) -> list[str]:
    """Seeded skills no availability gate can turn off: no declared requirements, no credential issuer."""
    skills = await service.list_skills(skill_type=SkillType.PREBUILT)
    ids = sorted(
        skill.id
        for skill in skills
        if skill.id not in ALL_INTEGRATION_GATED_SKILL_IDS
        and not skill.required_oauth_issuers
        and not (skill.requires.bins or skill.requires.env or skill.requires.config)
    )
    assert len(ids) >= 25, "the seeded set must cover the largest pick of these tests"
    return ids


def _configs(skill_ids: list[str], *, is_core: bool) -> SkillConfigs:
    return {skill_id: {"is_core": is_core} for skill_id in skill_ids}


async def _runtime_skills(service: SkillsService, skill_ids: list[str]) -> list[SkillMetadata]:
    """The skills the agent runtime loads for these ids: what `general_agent/factory.py` builds, then `SkillAgent` loads."""
    enabled = frozenset((await service.user_config.get_config()).enabled_prebuilt_ids)
    backend = await create_skill_backend(
        storage=service.storage,
        skill_ids=skill_ids,
        user_id="runtime-test",
        allowed_prebuilt_ids=enabled,
    )
    return await backend.load_skills(skill_ids)


@asynccontextmanager
async def _no_db_session() -> AsyncIterator[None]:
    yield None


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
    service: SkillsService, plain_ids: list[str]
) -> None:
    bound = plain_ids[:8]

    preview = await _build_catalog_preview(bound, _configs(bound, is_core=True))

    assert preview["inline_count"] == 8
    assert preview["hidden_count"] == 0
    assert preview["overflow_count"] == 0
    assert preview["catalog_tokens"] > 0
    assert preview["search_mounted"] is False


@pytest.mark.asyncio
async def test_build_catalog_preview_hidden_mounts_search(
    monkeypatch: pytest.MonkeyPatch, service: SkillsService, plain_ids: list[str]
) -> None:
    # The catalog is token-budgeted: shrink the budget so 25 core entries cannot all fit.
    monkeypatch.setattr(_CATALOG_BUDGET, 200)
    bound = plain_ids[:25]

    preview = await _build_catalog_preview(bound, _configs(bound, is_core=True))

    assert preview["hidden_count"] > 0
    assert preview["inline_count"] + preview["hidden_count"] == len(bound)
    assert preview["overflow_count"] == preview["hidden_count"]  # every skill is core, so each hidden one overflowed
    assert preview["search_mounted"] is True


@pytest.mark.asyncio
async def test_build_catalog_preview_peripheral_skills_are_named_not_overflowed(
    service: SkillsService, plain_ids: list[str]
) -> None:
    bound = plain_ids[:12]

    preview = await _build_catalog_preview(bound, _configs(bound, is_core=False))

    assert preview["inline_count"] == 0
    assert preview["hidden_count"] == 12
    assert preview["overflow_count"] == 0
    assert preview["catalog_tokens"] > 0  # the names line is part of the catalog
    assert preview["search_mounted"] is True


@pytest.mark.asyncio
async def test_build_catalog_preview_matches_the_runtime_catalog_for_an_empty_config(
    monkeypatch: pytest.MonkeyPatch, service: SkillsService, plain_ids: list[str]
) -> None:
    monkeypatch.setattr(_CATALOG_BUDGET, 200)
    bound = plain_ids[:25]

    preview = await _build_catalog_preview(bound, {})

    skills = await _runtime_skills(service, bound)
    runtime = render_bound_skills_catalog(skills, skill_configs=None)
    assert runtime is not None
    assert len(skills) == len(bound)
    assert preview["catalog_tokens"] == get_token_count(runtime.xml)
    assert preview["hidden_count"] == runtime.hidden_skill_count > 0
    assert preview["inline_count"] > 0  # no config means no peripheral choice: skills fill the budget
    assert preview["inline_count"] + preview["hidden_count"] == len(bound)


@pytest.mark.asyncio
async def test_build_catalog_preview_matches_the_runtime_catalog_for_peripheral_skills(
    service: SkillsService, plain_ids: list[str]
) -> None:
    bound = plain_ids[:40]
    configs = _configs(bound, is_core=False)

    preview = await _build_catalog_preview(bound, configs)

    runtime = render_bound_skills_catalog(await _runtime_skills(service, bound), skill_configs=configs)
    assert runtime is not None
    assert preview["catalog_tokens"] == get_token_count(runtime.xml)
    assert preview["hidden_count"] == runtime.hidden_skill_count == len(bound)


@pytest.mark.asyncio
async def test_build_catalog_preview_counts_a_local_skill_beside_prebuilt_ones(
    tmp_path: Path, service: SkillsService, plain_ids: list[str]
) -> None:
    local_root = tmp_path / "local-skills"
    (local_root / "probe-local").mkdir(parents=True)
    (local_root / "probe-local" / "SKILL.md").write_text(_LOCAL_SKILL_MD, encoding="utf-8")
    local_skills = LocalSkillsProvider([str(local_root)]).scan_all()
    config = await service.user_config.get_config()
    config.enabled_local_skill_ids = [skill.id for skill in local_skills]
    await service.user_config.save_config(config)
    bound = [local_skills[0].id, *plain_ids[:3]]

    with patch("app.core.skills.store.reader.list_local_skills", AsyncMock(return_value=local_skills)):
        preview = await _build_catalog_preview(bound, _configs(bound, is_core=True))

    assert preview["inline_count"] == 4


@pytest.mark.asyncio
async def test_build_catalog_preview_counts_skill_whose_keys_are_saved_in_settings(
    monkeypatch: pytest.MonkeyPatch, service: SkillsService
) -> None:
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.setattr(
        "app.core.skills.gates.requirements_availability._load_skill_env_vars",
        AsyncMock(return_value={"linear-project": {"LINEAR_API_KEY": "secret"}}),
    )

    preview = await _build_catalog_preview(["linear-project"], _configs(["linear-project"], is_core=True))

    assert preview["inline_count"] == 1


@pytest.mark.asyncio
async def test_build_catalog_preview_omits_skill_whose_keys_are_missing(
    monkeypatch: pytest.MonkeyPatch, service: SkillsService
) -> None:
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    monkeypatch.setattr(
        "app.core.skills.gates.requirements_availability._load_skill_env_vars",
        AsyncMock(return_value={}),
    )

    preview = await _build_catalog_preview(["linear-project"], _configs(["linear-project"], is_core=True))

    assert preview["inline_count"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(("connected", "expected_inline"), [(True, 1), (False, 0)])
async def test_build_catalog_preview_follows_the_integration_credential_gate(
    monkeypatch: pytest.MonkeyPatch, service: SkillsService, connected: bool, expected_inline: int
) -> None:
    monkeypatch.setattr("app.database.connection.get_session", _no_db_session)
    monkeypatch.setattr(
        "app.core.skills.gates.oauth_availability.is_oauth_issuer_connected",
        AsyncMock(return_value=connected),
    )

    preview = await _build_catalog_preview(["google-workspace"], _configs(["google-workspace"], is_core=True))

    assert preview["inline_count"] == expected_inline
