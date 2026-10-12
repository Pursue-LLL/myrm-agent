"""Requirement-based skill availability honours env keys saved in the skills settings.

The scenarios run the real prebuilt skill assets through ``StorageSkillBackend`` on a
temporary storage, so a skill's ``requires`` frontmatter, the saved ``skill_env_vars``
and the availability verdict are exercised end to end (no hand-built ``available=True``).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.backends.skills import StorageSkillBackend
from myrm_agent_harness.backends.skills.types import SkillMetadata, SkillRequires, SkillTrust
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend
from myrm_agent_harness.toolkits.storage.types import SkillType

from app.core.skills.gates.oauth_availability import (
    apply_integration_oauth_availability,
    wrap_integration_oauth_backend,
)
from app.core.skills.gates.requirements_availability import (
    apply_requirements_availability_to_catalog,
    apply_requirements_availability_to_metadata,
)
from app.core.skills.models import Skill
from app.core.skills.store.user_config import UserSkillConfigManager, lookup_skill_env

PREBUILT_ASSETS = Path(__file__).resolve().parents[4] / "assets" / "prebuilt_skills"
NOTION_KEY = "NOTION_API_KEY"
IMAP_KEYS = ("EMAIL_IMAP_HOST", "EMAIL_IMAP_USER", "EMAIL_IMAP_PASSWORD")


@pytest.fixture
def storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LocalStorageBackend:
    """Temporary storage with the user-config reader pointed at it and no ambient keys."""
    backend = LocalStorageBackend(tmp_path)
    monkeypatch.setattr("app.core.skills.gates.requirements_availability.get_storage_provider", lambda: backend)
    for key in (NOTION_KEY, *IMAP_KEYS):
        monkeypatch.delenv(key, raising=False)
    return backend


def _install(storage: LocalStorageBackend, *skill_ids: str) -> StorageSkillBackend:
    for skill_id in skill_ids:
        shutil.copytree(PREBUILT_ASSETS / skill_id, storage.base_path / "skills/prebuilt" / skill_id)
    return StorageSkillBackend(storage=storage, skills_prefix="skills/prebuilt", default_trust=SkillTrust.TRUSTED)


async def _save_env(storage: LocalStorageBackend, skill_env_vars: dict[str, dict[str, str]]) -> None:
    manager = UserSkillConfigManager(storage)
    config = await manager.get_config()
    config.skill_env_vars = skill_env_vars
    await manager.save_config(config)


async def _wrapped_skills(backend: StorageSkillBackend) -> dict[str, SkillMetadata]:
    skills = await wrap_integration_oauth_backend(backend).list_skills()
    return {skill.name: skill for skill in skills}


async def test_env_saved_in_settings_makes_the_skill_available(storage: LocalStorageBackend) -> None:
    backend = _install(storage, "notion-workspace", "github-workflow")
    await _save_env(storage, {"notion-workspace": {NOTION_KEY: "secret_from_settings_ui"}})

    skills = await _wrapped_skills(backend)

    assert skills["notion-workspace"].available is True
    assert skills["notion-workspace"].unavailable_reason is None


async def test_missing_env_keeps_the_skill_unavailable_with_the_variable_named(storage: LocalStorageBackend) -> None:
    backend = _install(storage, "notion-workspace")

    skills = await _wrapped_skills(backend)

    assert skills["notion-workspace"].available is False
    assert skills["notion-workspace"].unavailable_reason == f"Missing: ENV: {NOTION_KEY}"


async def test_blank_saved_value_does_not_count(storage: LocalStorageBackend) -> None:
    backend = _install(storage, "notion-workspace")
    await _save_env(storage, {"notion-workspace": {NOTION_KEY: "  "}})

    skills = await _wrapped_skills(backend)

    assert skills["notion-workspace"].available is False


async def test_process_environment_alone_still_satisfies(
    storage: LocalStorageBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = _install(storage, "notion-workspace")
    monkeypatch.setenv(NOTION_KEY, "secret_from_process_env")

    skills = await _wrapped_skills(backend)

    assert skills["notion-workspace"].available is True


async def test_env_saved_for_another_skill_is_not_borrowed(storage: LocalStorageBackend) -> None:
    backend = _install(storage, "notion-workspace")
    await _save_env(storage, {"linear-project": {NOTION_KEY: "belongs_to_a_different_skill"}})

    skills = await _wrapped_skills(backend)

    assert skills["notion-workspace"].available is False


async def test_every_declared_variable_is_required(storage: LocalStorageBackend) -> None:
    backend = _install(storage, "imap-smtp-email")
    await _save_env(storage, {"imap-smtp-email": {IMAP_KEYS[0]: "imap.example.com"}})

    partial = await _wrapped_skills(backend)
    assert partial["imap-smtp-email"].available is False
    assert partial["imap-smtp-email"].unavailable_reason == f"Missing: ENV: {IMAP_KEYS[1]}, ENV: {IMAP_KEYS[2]}"

    await _save_env(storage, {"imap-smtp-email": dict.fromkeys(IMAP_KEYS, "configured")})
    complete = await _wrapped_skills(backend)
    assert complete["imap-smtp-email"].available is True


@pytest.mark.parametrize("cli_on_path", [True, False])
async def test_declared_cli_follows_the_server_path(storage: LocalStorageBackend, cli_on_path: bool) -> None:
    backend = _install(storage, "xurl")

    with patch("shutil.which", return_value="/usr/local/bin/xurl" if cli_on_path else None):
        skills = await _wrapped_skills(backend)

    assert skills["xurl"].available is cli_on_path
    assert skills["xurl"].unavailable_reason == (None if cli_on_path else "Missing: CLI: xurl")


async def test_skill_without_declared_requirements_is_left_untouched(storage: LocalStorageBackend) -> None:
    meta = SkillMetadata(name="plain", description="no requirements", available=False, unavailable_reason="held back")

    await apply_requirements_availability_to_metadata([meta])

    assert meta.available is False
    assert meta.unavailable_reason == "held back"


async def test_unreadable_config_degrades_to_process_environment(
    storage: LocalStorageBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    meta = SkillMetadata(name="needs-key", description="d", requires=SkillRequires(env=["SKILL_REQ_PROBE_KEY"]))
    monkeypatch.setattr(
        "app.core.skills.gates.requirements_availability.get_storage_provider",
        lambda: (_ for _ in ()).throw(RuntimeError("storage offline")),
    )

    await apply_requirements_availability_to_metadata([meta])

    assert meta.available is False
    assert meta.unavailable_reason == "Missing: ENV: SKILL_REQ_PROBE_KEY"


async def test_catalog_cards_follow_the_same_verdict(storage: LocalStorageBackend) -> None:
    backend = _install(storage, "notion-workspace")
    await _save_env(storage, {"notion-workspace": {NOTION_KEY: "secret_from_settings_ui"}})
    meta = (await backend.list_skills())[0]
    assert meta.available is False, "the harness alone cannot see keys saved in settings"
    card = Skill.from_metadata(meta, skill_id="notion-workspace", skill_type=SkillType.PREBUILT)

    await apply_integration_oauth_availability([card], AsyncMock())

    assert card.available is True
    assert card.unavailable_reason is None


async def test_catalog_cards_are_downgraded_when_the_key_is_removed(storage: LocalStorageBackend) -> None:
    backend = _install(storage, "notion-workspace")
    meta = (await backend.list_skills())[0]
    card = Skill.from_metadata(meta, skill_id="notion-workspace", skill_type=SkillType.PREBUILT)
    card.available = True

    await apply_requirements_availability_to_catalog([card])

    assert card.available is False
    assert card.unavailable_reason == f"Missing: ENV: {NOTION_KEY}"


class TestLookupSkillEnv:
    """The saved-env lookup shared by availability and runtime injection."""

    def test_display_name_wins_over_storage_id(self) -> None:
        saved = {"notion-workspace": {"K": "by-name"}, "abc123": {"K": "by-id"}}
        assert lookup_skill_env(saved, "notion-workspace", "abc123") == {"K": "by-name"}

    def test_falls_back_to_storage_id(self) -> None:
        assert lookup_skill_env({"abc123": {"K": "by-id"}}, "My Skill", "abc123") == {"K": "by-id"}

    def test_unknown_skill_has_no_env(self) -> None:
        assert lookup_skill_env({"other": {"K": "v"}}, "My Skill", "abc123") is None

    def test_missing_storage_id_only_matches_by_name(self) -> None:
        assert lookup_skill_env({"other": {"K": "v"}}, "My Skill", None) is None
