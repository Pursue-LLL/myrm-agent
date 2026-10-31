"""The state root resolver: one answer for where Myrm-owned data lives."""

from __future__ import annotations

from pathlib import Path

import pytest

from myrm_agent_harness.infra import data_dir
from myrm_agent_harness.infra.data_dir import DATA_DIR_ENV, resolve_data_dir, resolve_workspace_state_dir


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway home directory with no state root override."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv(DATA_DIR_ENV, raising=False)
    return tmp_path / "home"


class TestResolveDataDir:
    def test_defaults_to_the_myrm_directory_in_the_home_directory(self, home: Path) -> None:
        assert resolve_data_dir() == home / ".myrm"

    def test_the_environment_variable_relocates_the_root(
        self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path / "isolated"))

        assert resolve_data_dir() == tmp_path / "isolated"

    def test_a_tilde_in_the_variable_expands_to_the_home_directory(
        self, home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(DATA_DIR_ENV, "~/profiles/work")

        assert resolve_data_dir() == home / "profiles" / "work"

    def test_surrounding_whitespace_in_the_variable_is_ignored(
        self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(DATA_DIR_ENV, f"  {tmp_path / 'isolated'}  ")

        assert resolve_data_dir() == tmp_path / "isolated"

    @pytest.mark.parametrize("blank", ["", "   ", "\t"])
    def test_a_blank_variable_means_the_default(self, home: Path, monkeypatch: pytest.MonkeyPatch, blank: str) -> None:
        monkeypatch.setenv(DATA_DIR_ENV, blank)

        assert resolve_data_dir() == home / ".myrm"

    def test_the_root_is_not_created_by_resolving_it(self, home: Path) -> None:
        resolve_data_dir()

        assert not home.exists()

    def test_the_variable_is_read_on_every_call(
        self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        first = resolve_data_dir()
        monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path / "later"))

        assert (first, resolve_data_dir()) == (home / ".myrm", tmp_path / "later")


class TestResolveWorkspaceStateDir:
    @staticmethod
    def _sandbox(monkeypatch: pytest.MonkeyPatch, *, present: bool) -> None:
        real_exists = data_dir.os.path.exists
        monkeypatch.setattr(
            data_dir.os.path, "exists", lambda path: present if path == "/workspace/" else real_exists(path)
        )

    def test_inside_a_sandbox_the_state_lives_with_the_workspace_volume(
        self, home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._sandbox(monkeypatch, present=True)

        assert resolve_workspace_state_dir() == Path("/workspace/.myrm")

    def test_an_explicit_root_wins_over_the_sandbox_volume(
        self, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._sandbox(monkeypatch, present=True)
        monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path / "isolated"))

        assert resolve_workspace_state_dir() == tmp_path / "isolated"

    def test_outside_a_sandbox_it_is_the_ordinary_root(self, home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._sandbox(monkeypatch, present=False)

        assert resolve_workspace_state_dir() == home / ".myrm"
