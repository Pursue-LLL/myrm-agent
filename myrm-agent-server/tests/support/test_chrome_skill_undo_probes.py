"""Unit tests: a failed live undo run names the frontend files saved while it ran, the usual cause of a hot reload."""

from __future__ import annotations

import os
from pathlib import Path

from tests.support.chrome_skill_undo_probes import recently_edited_frontend_files

_STARTED_AT = 1_000_000.0


def _save(root: Path, relative: str, modified: float) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("export {};\n", encoding="utf-8")
    os.utime(path, (modified, modified))


def test_lists_only_files_saved_after_the_start_newest_first(tmp_path: Path) -> None:
    _save(tmp_path, "store/old.ts", _STARTED_AT - 5)
    _save(tmp_path, "store/chat/first.ts", _STARTED_AT + 10)
    _save(tmp_path, "components/second.tsx", _STARTED_AT + 20)

    assert recently_edited_frontend_files(_STARTED_AT, root=tmp_path) == ["components/second.tsx", "store/chat/first.ts"]


def test_file_saved_exactly_at_the_start_is_not_an_edit_made_during_the_run(tmp_path: Path) -> None:
    _save(tmp_path, "store/at-start.ts", _STARTED_AT)

    assert recently_edited_frontend_files(_STARTED_AT, root=tmp_path) == []


def test_limit_keeps_the_newest_files(tmp_path: Path) -> None:
    for index in range(5):
        _save(tmp_path, f"store/file{index}.ts", _STARTED_AT + 1 + index)

    assert recently_edited_frontend_files(_STARTED_AT, root=tmp_path, limit=2) == ["store/file4.ts", "store/file3.ts"]


def test_missing_frontend_root_lists_nothing(tmp_path: Path) -> None:
    assert recently_edited_frontend_files(_STARTED_AT, root=tmp_path / "absent") == []
