"""Project payload: a bound folder that can no longer be used as a workspace is reported as such."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.database.models.project import Project
from app.services.project.project_service import _project_to_dict


def _project(workspace_path: str | None) -> Project:
    return Project(
        id="p1",
        name="Notes",
        description="",
        color="#7cb9ff",
        sort_order=0,
        workspace_path=workspace_path,
        goal_summary="",
    )


def test_a_project_without_a_folder_is_usable() -> None:
    payload = _project_to_dict(_project(None))
    assert payload["workspacePath"] == ""
    assert payload["workspaceUsable"] is True


def test_an_ordinary_folder_is_usable(tmp_path: Path) -> None:
    assert _project_to_dict(_project(str(tmp_path)))["workspaceUsable"] is True


@pytest.mark.parametrize("path", [str(Path.home()), "/"])
def test_a_folder_that_contains_protected_locations_is_reported_unusable(path: str) -> None:
    payload = _project_to_dict(_project(path))
    assert payload["workspacePath"] == path
    assert payload["workspaceUsable"] is False
