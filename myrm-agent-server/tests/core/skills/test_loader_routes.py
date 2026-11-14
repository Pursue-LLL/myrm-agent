"""The routes of an assembled skill backend, and what survives when one source cannot be read or built.

`test_loader_content_resolution.py` proves the assembled stack serves every skill it lists end to end. This file pins
the edges of the pieces it is assembled from: the LOCAL skill folders bound to an agent, the enabled prebuilt catalog,
the workspace skill directories, and the version-routing decorator that must never take the skills down with it.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.agent.security import CredentialTrack
from myrm_agent_harness.backends.skills import (
    CompositeSkillBackend,
    InMemorySkillBackend,
    LocalSkillBackend,
    SkillBackendProtocol,
)
from myrm_agent_harness.backends.skills.types import SkillMetadata

from app.core.skills import loader
from app.core.skills.gates.oauth_availability import IntegrationOAuthSkillBackend

_ALPHA = SkillMetadata(name="alpha", description="Alpha", storage_skill_id="prebuilt-alpha")
_BETA = SkillMetadata(name="beta", description="Beta", storage_skill_id="prebuilt-beta")


def _write_skill(skills_dir: Path, name: str) -> None:
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {name} skill\n---\n# {name}\n", encoding="utf-8")


def _local_skill(tmp_path: Path) -> SkillMetadata:
    skill_dir = tmp_path / "probe"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# probe\n", encoding="utf-8")
    (skill_dir / "notes.txt").write_text("notes", encoding="utf-8")
    (skill_dir / ".hidden").write_text("hidden", encoding="utf-8")
    return SkillMetadata(name="probe", description="Probe", storage_skill_id="local-probe", storage_path=str(skill_dir))


async def _names(backend: SkillBackendProtocol | None) -> set[str]:
    assert backend is not None
    return {skill.name for skill in await backend.list_skills()}


@pytest.fixture
def skills_service(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """The user-facing skill service the loader reads LOCAL skills and the enabled-prebuilt config from."""
    service = SimpleNamespace(
        user_config=SimpleNamespace(ensure_prebuilt_enabled_after_sync=AsyncMock()),
        get_skills_by_ids=AsyncMock(return_value=[]),
    )
    monkeypatch.setattr("app.core.skills.store.service.skills_service", service)
    return service


@pytest.fixture
def seed_sync(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """The prebuilt seed sync that runs on every assembly; by default it adds no skill."""
    sync = AsyncMock(return_value=SimpleNamespace(skill_ids=[]))
    monkeypatch.setattr("app.core.skills.prebuilt_sync.sync_prebuilt_seeds", sync)
    return sync


class TestUserSkillBackend:
    """The LOCAL skill folders bound to an agent."""

    async def test_serves_a_skill_by_its_name_or_its_storage_id(self, tmp_path: Path) -> None:
        backend = loader._UserSkillBackend([_local_skill(tmp_path)])  # noqa: SLF001

        assert await backend.get_skill_content("probe") == "# probe\n"
        assert await backend.get_skill_content("local-probe") == "# probe\n"
        assert [skill.name for skill in await backend.load_skills(["local-probe"])] == ["probe"]
        assert await backend.load_skills(["other"]) == []

    async def test_lists_the_files_beside_the_sop_but_not_hidden_ones(self, tmp_path: Path) -> None:
        backend = loader._UserSkillBackend([_local_skill(tmp_path)])  # noqa: SLF001

        assert await backend.list_skill_resources("probe") == ["notes.txt"]
        assert await backend.get_skill_resources("probe", "notes.txt") == b"notes"

    async def test_a_skill_it_does_not_hold_cannot_be_read(self) -> None:
        backend = loader._UserSkillBackend([])  # noqa: SLF001

        with pytest.raises(FileNotFoundError, match="User skill not found: ghost"):
            await backend.get_skill_content("ghost")
        with pytest.raises(FileNotFoundError, match="User skill not found: ghost"):
            await backend.get_skill_resources("ghost", "notes.txt")
        assert await backend.list_skill_resources("ghost") == []

    def test_a_folder_that_cannot_be_walked_has_no_resources(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def unreadable(self: Path, pattern: str) -> object:
            raise OSError("input/output error")

        monkeypatch.setattr(Path, "rglob", unreadable)

        assert loader._list_local_resources(tmp_path) == []  # noqa: SLF001


class TestEnabledPrebuiltBackend:
    """The enabled prebuilt skills: metadata held in memory, content and resources read from the prebuilt store."""

    @pytest.fixture
    def store(self) -> MagicMock:
        return MagicMock(
            get_skill_content=AsyncMock(return_value="sop"),
            get_skill_resources=AsyncMock(return_value=b"resource"),
            list_skill_resources=AsyncMock(return_value=["guide.md"]),
        )

    async def test_serves_an_enabled_skill_from_the_store_by_name_or_storage_id(self, store: MagicMock) -> None:
        backend = loader._EnabledPrebuiltBackend([_ALPHA], store)  # noqa: SLF001

        assert await backend.get_skill_content("alpha") == "sop"
        assert await backend.get_skill_resources("prebuilt-alpha", "guide.md") == b"resource"
        assert await backend.list_skill_resources("alpha") == ["guide.md"]
        store.get_skill_resources.assert_awaited_once_with("prebuilt-alpha", "guide.md")

    async def test_never_asks_the_store_for_a_skill_that_is_not_enabled(self, store: MagicMock) -> None:
        backend = loader._EnabledPrebuiltBackend([_ALPHA], store)  # noqa: SLF001

        with pytest.raises(FileNotFoundError, match="Prebuilt skill not enabled: beta"):
            await backend.get_skill_content("beta")
        with pytest.raises(FileNotFoundError, match="Prebuilt skill not enabled: beta"):
            await backend.get_skill_resources("beta", "guide.md")
        assert await backend.list_skill_resources("beta") == []
        store.get_skill_content.assert_not_called()
        store.get_skill_resources.assert_not_called()
        store.list_skill_resources.assert_not_called()


class TestWorkspaceSkillBackend:
    """The skill directories a project carries, from this product and from other harnesses."""

    @pytest.mark.parametrize("workspace", [None, ""], ids=["none", "empty"])
    def test_no_workspace_means_no_workspace_skills(self, workspace: str | None) -> None:
        assert loader._load_workspace_skill_backend(workspace) is None  # noqa: SLF001

    def test_a_workspace_that_is_not_a_directory_has_none(self, tmp_path: Path) -> None:
        assert loader._load_workspace_skill_backend(str(tmp_path / "missing")) is None  # noqa: SLF001

    def test_a_workspace_whose_skill_directories_are_absent_or_empty_has_none(self, tmp_path: Path) -> None:
        (tmp_path / ".cursor" / "skills").mkdir(parents=True)

        assert loader._load_workspace_skill_backend(str(tmp_path)) is None  # noqa: SLF001

    async def test_a_single_skill_directory_is_served_directly(self, tmp_path: Path) -> None:
        _write_skill(tmp_path / ".cursor" / "skills", "only")

        backend = loader._load_workspace_skill_backend(str(tmp_path))  # noqa: SLF001

        assert isinstance(backend, LocalSkillBackend)
        assert await _names(backend) == {"only"}

    async def test_several_skill_directories_are_served_side_by_side(self, tmp_path: Path) -> None:
        _write_skill(tmp_path / ".cursor" / "skills", "from-cursor")
        _write_skill(tmp_path / ".claude" / "skills", "from-claude")

        backend = loader._load_workspace_skill_backend(str(tmp_path))  # noqa: SLF001

        assert isinstance(backend, CompositeSkillBackend)
        assert sorted(backend.routes) == ["/src_0/", "/src_1/"]
        assert await _names(backend) == {"from-cursor", "from-claude"}

    async def test_a_directory_the_harness_rejects_is_skipped_and_the_others_still_load(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        (tmp_path / ".cursor" / "skills").mkdir(parents=True)
        (tmp_path / ".cursor" / "skills" / "stray.txt").write_text("not a skill", encoding="utf-8")
        _write_skill(tmp_path / ".claude" / "skills", "kept")
        real_backend = loader.LocalSkillBackend

        def build(path: Path) -> LocalSkillBackend:
            if ".cursor" in str(path):
                raise ValueError("not a skills directory")
            return real_backend(path)

        monkeypatch.setattr(loader, "LocalSkillBackend", build)

        with caplog.at_level(logging.WARNING, logger=loader.logger.name):
            backend = loader._load_workspace_skill_backend(str(tmp_path))  # noqa: SLF001

        assert await _names(backend) == {"kept"}
        assert "not a skills directory" in caplog.text


class TestUserSkillLoading:
    """Binding LOCAL skills to an agent: whatever goes wrong, the agent still starts."""

    async def test_an_unreachable_catalog_means_no_local_skills_and_an_error_in_the_log(
        self, skills_service: SimpleNamespace, caplog: pytest.LogCaptureFixture
    ) -> None:
        skills_service.get_skills_by_ids.side_effect = RuntimeError("catalog down")

        with caplog.at_level(logging.ERROR, logger=loader.logger.name):
            assert await loader._load_user_skill_backend(["s1"], "user-1") is None  # noqa: SLF001

        assert "Failed to load user skills for user-1: catalog down" in caplog.text

    async def test_no_local_skill_found_means_no_user_route(self, skills_service: SimpleNamespace) -> None:
        assert await loader._load_user_skill_backend(["s1"], "user-1") is None  # noqa: SLF001

    async def test_a_skill_with_an_invalid_name_is_skipped_and_the_rest_are_served(
        self, skills_service: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        skills_service.get_skills_by_ids.return_value = [SimpleNamespace(name="Bad Name"), SimpleNamespace(name="good")]

        def to_metadata(skill: SimpleNamespace) -> SkillMetadata:
            if skill.name == "Bad Name":
                raise ValueError("invalid skill name")
            return SkillMetadata(name=skill.name, description="Good")

        monkeypatch.setattr("app.core.skills.runtime_metadata.skill_to_runtime_metadata", to_metadata)

        with caplog.at_level(logging.WARNING, logger=loader.logger.name):
            backend = await loader._load_user_skill_backend(["s1", "s2"], "user-1")  # noqa: SLF001

        assert backend is not None
        assert await _names(backend) == {"good"}
        assert "Skipping skill with invalid name 'Bad Name': invalid skill name" in caplog.text


class _VersionRouted:
    """Stands in for the harness decorator that serves the activated version snapshot: it serves what its base serves."""

    def __init__(self, base_backend: object, snapshot_store: object) -> None:
        self.base_backend = base_backend
        self.snapshot_store = snapshot_store

    def __getattr__(self, name: str) -> object:
        return getattr(self.base_backend, name)


class TestCreateSkillBackend:
    """Which sources an agent's backend is assembled from, and the decorators around it."""

    @pytest.fixture
    def prebuilt(
        self, monkeypatch: pytest.MonkeyPatch, skills_service: SimpleNamespace, seed_sync: AsyncMock
    ) -> InMemorySkillBackend:
        """The prebuilt catalog (alpha, beta), with the version store stood in for."""
        store = InMemorySkillBackend(skills=[_ALPHA, _BETA])
        monkeypatch.setattr(loader, "StorageSkillBackend", lambda **_: store)
        monkeypatch.setattr(loader, "VersionAwareSkillBackend", _VersionRouted)
        monkeypatch.setattr("app.platform_utils.get_session_factory", MagicMock)
        return store

    async def test_skills_the_seed_sync_just_added_are_enabled_for_the_user(
        self, prebuilt: InMemorySkillBackend, skills_service: SimpleNamespace, seed_sync: AsyncMock
    ) -> None:
        seed_sync.return_value = SimpleNamespace(skill_ids=("prebuilt-alpha", "prebuilt-beta"))

        await loader.create_skill_backend(MagicMock())

        skills_service.user_config.ensure_prebuilt_enabled_after_sync.assert_awaited_once_with(
            ["prebuilt-alpha", "prebuilt-beta"]
        )

    async def test_a_sync_that_adds_nothing_changes_nothing_in_the_user_config(
        self, prebuilt: InMemorySkillBackend, skills_service: SimpleNamespace
    ) -> None:
        await loader.create_skill_backend(MagicMock())

        skills_service.user_config.ensure_prebuilt_enabled_after_sync.assert_not_awaited()

    async def test_a_whitelist_that_matches_no_prebuilt_skill_serves_nothing(self, prebuilt: InMemorySkillBackend) -> None:
        backend = await loader.create_skill_backend(MagicMock(), allowed_prebuilt_ids=frozenset({"unknown"}))

        assert await backend.list_skills() == []

    async def test_without_a_whitelist_the_prebuilt_catalog_is_served_as_it_is(self, prebuilt: InMemorySkillBackend) -> None:
        backend = await loader.create_skill_backend(MagicMock())

        assert await _names(backend) == {"alpha", "beta"}

    async def test_without_a_whitelist_the_prebuilt_catalog_is_the_default_beside_the_workspace_skills(
        self, prebuilt: InMemorySkillBackend, tmp_path: Path
    ) -> None:
        _write_skill(tmp_path / ".cursor" / "skills", "from-workspace")

        backend = await loader.create_skill_backend(MagicMock(), workspace_path=str(tmp_path))

        assert await _names(backend) == {"alpha", "beta", "from-workspace"}

    async def test_the_backend_is_wrapped_for_version_routing_and_the_credential_track(
        self, prebuilt: InMemorySkillBackend
    ) -> None:
        backend = await loader.create_skill_backend(MagicMock(), credential_track=CredentialTrack.SHARED)

        assert isinstance(backend, IntegrationOAuthSkillBackend)
        assert backend._credential_track is CredentialTrack.SHARED  # noqa: SLF001
        assert isinstance(backend._base, _VersionRouted)  # noqa: SLF001
        assert backend._base.base_backend is prebuilt  # noqa: SLF001

    async def test_a_version_store_that_cannot_be_imported_leaves_the_plain_backend(
        self, prebuilt: InMemorySkillBackend, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setitem(sys.modules, "app.core.skills.storage_adapters", None)

        with caplog.at_level(logging.WARNING, logger=loader.logger.name):
            backend = await loader.create_skill_backend(MagicMock())

        assert backend._base is prebuilt  # noqa: SLF001
        assert "Skill optimization storage not available" in caplog.text

    async def test_a_version_store_that_fails_to_build_leaves_the_plain_backend(
        self, prebuilt: InMemorySkillBackend, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        def no_database() -> object:
            raise RuntimeError("no database")

        monkeypatch.setattr("app.platform_utils.get_session_factory", no_database)

        with caplog.at_level(logging.ERROR, logger=loader.logger.name):
            backend = await loader.create_skill_backend(MagicMock())

        assert backend._base is prebuilt  # noqa: SLF001
        assert "Failed to initialize VersionAwareSkillBackend: no database" in caplog.text
