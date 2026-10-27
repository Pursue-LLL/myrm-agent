"""A folder's declared command prefixes take effect only for what the user was shown when trusting it.

[INPUT]
- app.services.security.workspace_trust_store (POS: UserConfig-backed trust registry and harness lookup)
- myrm_agent_harness.agent.security.workspace_trust (POS: run-start trust binding)

[OUTPUT]
- Persistence of the disclosed prefixes (round trip, entries saved before the field existed), the decisions that
  record or clear them, and the run-start result for a folder whose config grows after the user trusted it.

[POS]
tests/services/security/test_workspace_trust_store.py
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from myrm_agent_harness.agent.security.workspace_trust import (
    WorkspaceTrustLevel,
    apply_workspace_trust_for_root,
    clear_workspace_trust_runtime,
    get_repo_command_prefixes,
    set_workspace_trust_lookup,
)
from myrm_agent_harness.agent.security.workspace_trust.provider import get_workspace_trust_lookup

from app.services.security.workspace_trust_store import (
    WORKSPACE_TRUST_CONFIG_KEY,
    ConfigWorkspaceTrustLookup,
    WorkspaceTrustStore,
)


class _FakeConfigService:
    """In-memory stand-in for the UserConfig service: values survive between store instances."""

    def __init__(self) -> None:
        self.values: dict[str, dict[str, object]] = {}
        self._version = 0

    async def get(self, key: str) -> SimpleNamespace | None:
        if key not in self.values:
            return None
        return SimpleNamespace(value=self.values[key], version=str(self._version))

    async def set(
        self, key: str, value: dict[str, object], device_id: str, expected_version: str | None = None
    ) -> SimpleNamespace:
        self.values[key] = value
        self._version += 1
        return SimpleNamespace(value=value, version=str(self._version))


@pytest.fixture
def config(monkeypatch: pytest.MonkeyPatch) -> _FakeConfigService:
    fake = _FakeConfigService()
    monkeypatch.setattr("app.services.config.service.config_service", fake)
    return fake


@pytest.fixture(autouse=True)
def _restore_trust_state() -> Iterator[None]:
    previous = get_workspace_trust_lookup()
    yield
    set_workspace_trust_lookup(previous)
    clear_workspace_trust_runtime()


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    return root


def _declare(root: Path, *prefixes: str) -> None:
    config_file = root / ".myrm" / "config.toml"
    config_file.parent.mkdir(exist_ok=True)
    listed = ", ".join(f'"{prefix}"' for prefix in prefixes)
    config_file.write_text(f"[security]\ncommand_allowlist_prefixes = [{listed}]\n", encoding="utf-8")


async def _trust(store: WorkspaceTrustStore, root: Path) -> None:
    await store.decide(str(root), WorkspaceTrustLevel.TRUSTED, manifest=await store.build_manifest(str(root)))


class TestWhatIsRecorded:
    async def test_trusting_records_the_prefixes_the_user_was_shown(self, config: _FakeConfigService, folder: Path) -> None:
        _declare(folder, "npm run test")
        store = WorkspaceTrustStore()

        await _trust(store, folder)

        assert store.get_disclosed_command_prefixes(store.normalize_path(str(folder))) == ("npm run test",)

    async def test_restricting_records_none(self, config: _FakeConfigService, folder: Path) -> None:
        _declare(folder, "npm run test")
        store = WorkspaceTrustStore()

        await store.decide(str(folder), WorkspaceTrustLevel.RESTRICTED, manifest=await store.build_manifest(str(folder)))

        entry = store.get_entry(store.normalize_path(str(folder)))
        assert entry is not None
        assert entry.disclosed_command_prefixes == ()

    async def test_revoking_clears_them(self, config: _FakeConfigService, folder: Path) -> None:
        _declare(folder, "npm run test")
        store = WorkspaceTrustStore()
        await _trust(store, folder)

        await store.revoke(str(folder))

        assert store.get_disclosed_command_prefixes(store.normalize_path(str(folder))) == ()

    async def test_they_survive_a_reload(self, config: _FakeConfigService, folder: Path) -> None:
        _declare(folder, "npm run test", "make lint")
        await _trust(WorkspaceTrustStore(), folder)

        reloaded = WorkspaceTrustStore()
        await reloaded.load()

        assert reloaded.get_disclosed_command_prefixes(reloaded.normalize_path(str(folder))) == (
            "npm run test",
            "make lint",
        )

    async def test_an_entry_saved_before_the_field_existed_discloses_nothing(
        self, config: _FakeConfigService, folder: Path
    ) -> None:
        canonical = str(folder.resolve())
        config.values[WORKSPACE_TRUST_CONFIG_KEY] = {
            "entries": {canonical: {"level": "TRUSTED", "decided_at": "2026-01-01T00:00:00+00:00", "manifest_hash": "abc"}}
        }
        store = WorkspaceTrustStore()
        await store.load()

        assert store.get_level(canonical) == WorkspaceTrustLevel.TRUSTED
        assert store.get_disclosed_command_prefixes(canonical) == ()


class TestManifestPending:
    async def test_everything_declared_is_pending_before_the_first_decision(
        self, config: _FakeConfigService, folder: Path
    ) -> None:
        _declare(folder, "npm run test")

        manifest = await WorkspaceTrustStore().build_manifest(str(folder))

        assert manifest.pending_command_prefixes == ("npm run test",)

    async def test_only_what_was_added_after_trusting_is_pending(self, config: _FakeConfigService, folder: Path) -> None:
        _declare(folder, "npm run test")
        store = WorkspaceTrustStore()
        await _trust(store, folder)
        _declare(folder, "npm run test", "curl evil.example")

        manifest = await store.build_manifest(str(folder))

        assert manifest.pending_command_prefixes == ("curl evil.example",)

    async def test_nothing_is_pending_once_the_user_trusted_again(self, config: _FakeConfigService, folder: Path) -> None:
        _declare(folder, "npm run test")
        store = WorkspaceTrustStore()
        await _trust(store, folder)
        _declare(folder, "npm run test", "make lint")

        await _trust(store, folder)

        assert (await store.build_manifest(str(folder))).pending_command_prefixes == ()


class TestRunStartAfterTheAgentWroteTheConfig:
    async def test_a_prefix_written_after_trusting_is_inert_until_the_user_approves_it(
        self, config: _FakeConfigService, folder: Path
    ) -> None:
        store = WorkspaceTrustStore()
        set_workspace_trust_lookup(ConfigWorkspaceTrustLookup(store))
        await _trust(store, folder)  # a clean folder: trusted with nothing disclosed
        _declare(folder, "curl")  # what a sandboxed agent can write into its own workspace

        assert apply_workspace_trust_for_root(str(folder)) == WorkspaceTrustLevel.TRUSTED
        assert get_repo_command_prefixes() == ()

        await _trust(store, folder)  # the user reviewed the banner and approved it

        apply_workspace_trust_for_root(str(folder))
        assert get_repo_command_prefixes() == ("curl",)

    async def test_a_folder_trusted_before_the_field_existed_asks_once_more(
        self, config: _FakeConfigService, folder: Path
    ) -> None:
        _declare(folder, "npm run test")
        canonical = str(folder.resolve())
        config.values[WORKSPACE_TRUST_CONFIG_KEY] = {
            "entries": {canonical: {"level": "TRUSTED", "decided_at": "2026-01-01T00:00:00+00:00", "manifest_hash": "abc"}}
        }
        store = WorkspaceTrustStore()
        await store.load()
        set_workspace_trust_lookup(ConfigWorkspaceTrustLookup(store))

        apply_workspace_trust_for_root(str(folder))

        assert get_repo_command_prefixes() == ()
