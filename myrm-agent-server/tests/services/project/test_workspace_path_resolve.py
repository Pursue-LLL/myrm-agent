"""Tests for project workspace path normalization."""

from __future__ import annotations

import pytest

from app.services.project.workspace_path_resolve import (
    WorkspacePathValidationError,
    normalize_project_workspace_path,
)


def test_empty_clears_bind() -> None:
    assert normalize_project_workspace_path("") == ""
    assert normalize_project_workspace_path("   ") == ""


def test_resolves_absolute_unix_path(tmp_path) -> None:
    resolved = normalize_project_workspace_path(str(tmp_path))
    assert resolved == str(tmp_path.resolve())


def test_expands_tilde_path(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    child = tmp_path / "vault"
    child.mkdir()
    resolved = normalize_project_workspace_path("~/vault")
    assert resolved == str(child.resolve())


def test_rejects_relative_path() -> None:
    with pytest.raises(WorkspacePathValidationError, match="absolute"):
        normalize_project_workspace_path("relative/path")


def test_rejects_dot_relative_path() -> None:
    with pytest.raises(WorkspacePathValidationError, match="absolute"):
        normalize_project_workspace_path("./local/dir")
