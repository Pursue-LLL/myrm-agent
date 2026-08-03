"""Tests for prune_dead_runtime_cells."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from e2e_runtime_cell import (  # noqa: E402
    _CELL_META_FILE,
    _cell_dir,
    count_live_runtime_cells,
    prune_dead_runtime_cells,
)


@pytest.fixture(autouse=True)
def _state_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MYRM_DEV_STATE_DIR", str(tmp_path))


def test_prune_dead_runtime_cells_removes_dead_owner() -> None:
    cell_id = "cell-dead123"
    cell_path = _cell_dir(cell_id)
    cell_path.mkdir(parents=True)
    meta = {"cellId": cell_id, "runId": "run-x", "pid": 999999999, "acquiredAt": 0.0}
    (cell_path / _CELL_META_FILE).write_text(json.dumps(meta), encoding="utf-8")

    assert count_live_runtime_cells() == 0
    pruned = prune_dead_runtime_cells()
    assert pruned == 1
    assert not cell_path.exists()


def test_prune_dead_runtime_cells_keeps_live_owner() -> None:
    cell_id = "cell-live123"
    cell_path = _cell_dir(cell_id)
    cell_path.mkdir(parents=True)
    meta = {"cellId": cell_id, "runId": "run-y", "pid": os.getpid(), "acquiredAt": 0.0}
    (cell_path / _CELL_META_FILE).write_text(json.dumps(meta), encoding="utf-8")

    assert count_live_runtime_cells() == 1
    pruned = prune_dead_runtime_cells()
    assert pruned == 0
    assert cell_path.is_dir()
