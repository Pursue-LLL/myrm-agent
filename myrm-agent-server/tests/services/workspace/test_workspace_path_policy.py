"""Workspace path policy: what may become a workspace, and how a refusal reaches the client."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.workspace.workspace_path_policy import (
    WorkspacePathIssue,
    WorkspacePathValidationError,
    ensure_root_grantable,
    is_workspace_root_grantable,
    require_grantable_roots,
    resolve_optional_workspace_path,
    resolve_workspace_path,
    workspace_path_http_error,
)

HOME = str(Path.home())


@pytest.fixture
def state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "outer" / "state"
    folder.mkdir(parents=True)
    monkeypatch.setattr(
        "app.config.settings.get_settings",
        lambda: SimpleNamespace(database=SimpleNamespace(state_dir=str(folder))),
    )
    return folder


def _issue(raw: str, **kwargs: bool) -> WorkspacePathIssue:
    with pytest.raises(WorkspacePathValidationError) as excinfo:
        resolve_workspace_path(raw, **kwargs)
    return excinfo.value.issue


class TestResolveWorkspacePath:
    def test_existing_directory_is_canonicalized(self, tmp_path: Path) -> None:
        assert resolve_workspace_path(f"  {tmp_path}  ") == os.path.realpath(tmp_path)

    def test_tilde_is_expanded_to_the_folder_it_names(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / "vault").mkdir()
        assert resolve_workspace_path("~/vault") == os.path.realpath(tmp_path / "vault")

    @pytest.mark.parametrize("raw", ["", "   ", "relative/dir", "./dir"])
    def test_non_absolute_is_refused(self, raw: str) -> None:
        assert _issue(raw) is WorkspacePathIssue.NOT_ABSOLUTE

    @pytest.mark.parametrize("raw", ["~", HOME, os.path.dirname(HOME), "/"])
    def test_a_folder_that_contains_protected_locations_is_too_broad(self, raw: str) -> None:
        assert _issue(raw) is WorkspacePathIssue.TOO_BROAD

    def test_a_protected_location_itself_is_dangerous(self) -> None:
        assert _issue(os.path.join(HOME, ".ssh")) is WorkspacePathIssue.DANGEROUS

    def test_the_state_directory_and_its_ancestors_are_too_broad(self, state_dir: Path) -> None:
        assert _issue(str(state_dir)) is WorkspacePathIssue.TOO_BROAD
        assert _issue(str(state_dir.parent)) is WorkspacePathIssue.TOO_BROAD

    def test_a_workspace_below_the_state_directory_is_fine(self, state_dir: Path) -> None:
        chat_workspace = state_dir / "harness" / "workspaces" / "chat_1"
        chat_workspace.mkdir(parents=True)
        assert resolve_workspace_path(str(chat_workspace)) == os.path.realpath(chat_workspace)

    def test_a_symlink_to_the_state_directory_is_judged_by_its_target(self, state_dir: Path, tmp_path: Path) -> None:
        link = tmp_path / "shortcut"
        link.symlink_to(state_dir, target_is_directory=True)
        assert _issue(str(link)) is WorkspacePathIssue.TOO_BROAD

    def test_a_symlink_to_home_is_judged_by_its_target(self, tmp_path: Path) -> None:
        link = tmp_path / "innocent"
        link.symlink_to(HOME, target_is_directory=True)
        assert _issue(str(link)) is WorkspacePathIssue.TOO_BROAD

    def test_a_file_is_not_a_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "notes.txt"
        target.write_text("x", encoding="utf-8")
        assert _issue(str(target)) is WorkspacePathIssue.NOT_A_DIRECTORY

    def test_a_missing_path_needs_require_directory_to_be_refused(self, tmp_path: Path) -> None:
        missing = str(tmp_path / "later")
        assert resolve_workspace_path(missing) == os.path.realpath(missing)
        assert _issue(missing, require_directory=True) is WorkspacePathIssue.NOT_A_DIRECTORY

    def test_allow_broad_only_waives_the_breadth_check(self) -> None:
        assert resolve_workspace_path(HOME, require_directory=True, allow_broad=True) == os.path.realpath(HOME)
        assert _issue(os.path.join(HOME, ".ssh"), allow_broad=True) is WorkspacePathIssue.DANGEROUS


class TestIsWorkspaceRootGrantable:
    def test_home_and_filesystem_root_are_not(self) -> None:
        assert not is_workspace_root_grantable(HOME)
        assert not is_workspace_root_grantable("/")

    def test_ordinary_folders_are(self, tmp_path: Path) -> None:
        assert is_workspace_root_grantable(str(tmp_path))

    def test_a_workspace_nested_in_a_protected_root_stays_usable(self) -> None:
        """Container deployments keep their workspace under a protected root such as /root."""
        assert is_workspace_root_grantable(os.path.join(HOME, ".config", "myrm-workspace"))

    def test_the_state_directory_and_its_ancestors_are_not(self, state_dir: Path) -> None:
        assert not is_workspace_root_grantable(str(state_dir))
        assert not is_workspace_root_grantable(str(state_dir.parent))

    def test_a_chat_workspace_below_the_state_directory_is(self, state_dir: Path) -> None:
        chat_workspace = state_dir / "harness" / "workspaces" / "chat_1"
        chat_workspace.mkdir(parents=True)
        assert is_workspace_root_grantable(str(chat_workspace))

    def test_a_symlink_to_the_state_directory_is_judged_by_its_target(self, state_dir: Path, tmp_path: Path) -> None:
        link = tmp_path / "shortcut"
        link.symlink_to(state_dir, target_is_directory=True)
        assert not is_workspace_root_grantable(str(link))

    def test_it_agrees_with_the_gate_on_breadth(self, state_dir: Path, tmp_path: Path) -> None:
        """A folder is never bindable yet unusable, nor usable yet unbindable."""
        below = state_dir / "chat"
        below.mkdir()
        for folder in (HOME, "/", str(state_dir), str(state_dir.parent), str(below), str(tmp_path)):
            try:
                resolve_workspace_path(folder)
                bindable = True
            except WorkspacePathValidationError as exc:
                assert exc.issue is WorkspacePathIssue.TOO_BROAD
                bindable = False
            assert bindable is is_workspace_root_grantable(folder), folder


class TestResolveOptionalWorkspacePath:
    @pytest.mark.parametrize("raw", [None, "", "   "])
    def test_absent_and_blank_pass_unchanged(self, raw: str | None) -> None:
        assert resolve_optional_workspace_path(raw) == raw

    def test_a_value_goes_through_the_gate(self, tmp_path: Path) -> None:
        assert resolve_optional_workspace_path(str(tmp_path)) == os.path.realpath(tmp_path)
        with pytest.raises(WorkspacePathValidationError):
            resolve_optional_workspace_path(HOME)


class TestEnsureRootGrantable:
    def test_a_file_or_a_missing_folder_is_fine(self, tmp_path: Path) -> None:
        note = tmp_path / "todo.md"
        note.write_text("x", encoding="utf-8")
        ensure_root_grantable(str(note))
        ensure_root_grantable(str(tmp_path / "later"))

    @pytest.mark.parametrize(
        ("raw", "issue"),
        [
            (HOME, WorkspacePathIssue.TOO_BROAD),
            ("/", WorkspacePathIssue.TOO_BROAD),
            (os.path.join(HOME, ".ssh", "id_rsa"), WorkspacePathIssue.DANGEROUS),
            ("relative", WorkspacePathIssue.NOT_ABSOLUTE),
        ],
    )
    def test_the_checks_that_protect_locations_still_apply(self, raw: str, issue: WorkspacePathIssue) -> None:
        with pytest.raises(WorkspacePathValidationError) as excinfo:
            ensure_root_grantable(raw)
        assert excinfo.value.issue is issue


class TestRequireGrantableRoots:
    def test_ordinary_roots_pass(self, tmp_path: Path) -> None:
        require_grantable_roots([str(tmp_path), "~/Documents"], subject="Job a")

    def test_the_message_names_the_subject_and_the_root(self) -> None:
        with pytest.raises(WorkspacePathValidationError) as excinfo:
            require_grantable_roots(["/tmp", HOME], subject="Job a")
        assert excinfo.value.issue is WorkspacePathIssue.TOO_BROAD
        assert str(excinfo.value).startswith("Job a: ")
        assert repr(HOME) in str(excinfo.value)

    def test_a_tilde_root_is_judged_by_the_folder_it_names(self, state_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(state_dir))
        with pytest.raises(WorkspacePathValidationError):
            require_grantable_roots(["~"], subject="Job a")


def test_http_error_names_the_field_and_the_issue() -> None:
    error = WorkspacePathValidationError(WorkspacePathIssue.TOO_BROAD, "too broad")
    response = workspace_path_http_error(error, field="workspace_dir")
    assert response.status_code == 400
    assert isinstance(response.detail, dict)
    assert response.detail["error"]["details"] == [{"field": "workspace_dir", "issue": "too_broad"}]
