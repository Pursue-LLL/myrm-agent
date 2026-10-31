"""Tests for legacy canvas data directory cleanup."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.database.operations import legacy_canvas_cleanup as cleanup_mod


def test_remove_retired_canvas_data_dir_deletes_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canvas_root = tmp_path / "canvas"
    board_dir = canvas_root / "00000000-0000-4000-8000-000000000001"
    board_dir.mkdir(parents=True)
    (board_dir / "snapshot.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("MYRM_DATA_DIR", str(tmp_path))

    cleanup_mod.remove_retired_canvas_data_dir()

    assert not canvas_root.exists()


def test_remove_retired_canvas_data_dir_noop_when_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MYRM_DATA_DIR", str(tmp_path))

    cleanup_mod.remove_retired_canvas_data_dir()

    assert not (tmp_path / "canvas").exists()


def test_remove_retired_canvas_data_dir_leaves_the_home_directory_alone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A runtime with its own state root must never delete another profile's data under the home directory."""
    home_canvas = tmp_path / "home" / ".myrm" / "canvas" / "board"
    home_canvas.mkdir(parents=True)
    (home_canvas / "snapshot.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MYRM_DATA_DIR", str(tmp_path / "isolated"))

    cleanup_mod.remove_retired_canvas_data_dir()

    assert (home_canvas / "snapshot.json").is_file()
