"""Tests for retired Infinite Canvas filesystem cleanup."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.database import legacy_canvas_cleanup as cleanup_mod


def test_remove_retired_canvas_data_dir_deletes_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canvas_root = tmp_path / "canvas"
    board_dir = canvas_root / "00000000-0000-4000-8000-000000000001"
    board_dir.mkdir(parents=True)
    (board_dir / "snapshot.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cleanup_mod, "RETIRED_CANVAS_DATA_DIR", canvas_root)

    cleanup_mod.remove_retired_canvas_data_dir()

    assert not canvas_root.exists()


def test_remove_retired_canvas_data_dir_noop_when_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = tmp_path / "missing"
    monkeypatch.setattr(cleanup_mod, "RETIRED_CANVAS_DATA_DIR", missing)

    cleanup_mod.remove_retired_canvas_data_dir()

    assert not missing.exists()
