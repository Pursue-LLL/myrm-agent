"""``Artifact.source_path`` encoding: workspace-relative inside the workspace, absolute outside, one value per file."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.core.artifacts.source_path import from_source_path, to_source_path


def _page(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("<h1>page</h1>", encoding="utf-8")
    return path


def test_a_file_inside_the_workspace_is_stored_relative_to_it(tmp_path: Path) -> None:
    page = _page(tmp_path / "ws" / "site-a" / "index.html")

    assert to_source_path(str(page), str(tmp_path / "ws")) == "site-a/index.html"


def test_a_file_outside_the_workspace_is_stored_absolute(tmp_path: Path) -> None:
    page = _page(tmp_path / "elsewhere" / "index.html")
    (tmp_path / "ws").mkdir()

    assert to_source_path(str(page), str(tmp_path / "ws")) == page.resolve().as_posix()


def test_a_sibling_directory_sharing_the_workspace_prefix_is_outside_it(tmp_path: Path) -> None:
    page = _page(tmp_path / "ws-other" / "index.html")
    (tmp_path / "ws").mkdir()

    assert to_source_path(str(page), str(tmp_path / "ws")) == page.resolve().as_posix()


def test_every_spelling_of_a_file_stores_the_same_value(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "ws"
    page = _page(workspace / "site-a" / "index.html")
    monkeypatch.chdir(workspace)

    spellings = ["site-a/index.html", "./site-a/../site-a/index.html", str(page), f"{workspace}/site-a/./index.html"]

    assert {to_source_path(spelling, str(workspace)) for spelling in spellings} == {"site-a/index.html"}


@pytest.mark.skipif(os.name == "nt", reason="creating symlinks needs elevated rights on Windows")
def test_a_symlinked_workspace_root_gives_the_same_value(tmp_path: Path) -> None:
    page = _page(tmp_path / "real-ws" / "site-a" / "index.html")
    link = tmp_path / "linked-ws"
    link.symlink_to(tmp_path / "real-ws")

    assert (
        to_source_path(str(page), str(link))
        == to_source_path(str(link / "site-a" / "index.html"), str(link))
        == "site-a/index.html"
    )


def test_the_stored_value_names_the_file_again(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    inside = _page(workspace / "site-a" / "index.html")
    outside = _page(tmp_path / "elsewhere" / "index.html")

    assert from_source_path(workspace, to_source_path(str(inside), str(workspace))) == inside.resolve()
    assert from_source_path(workspace, to_source_path(str(outside), str(workspace))) == outside.resolve()


def test_an_absolute_source_path_ignores_the_workspace_root(tmp_path: Path) -> None:
    absolute = tmp_path / "elsewhere" / "index.html"

    assert from_source_path(tmp_path / "ws", absolute.as_posix()) == absolute
