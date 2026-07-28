"""Unit tests for e2e_runtime_cell (R73-F)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from e2e_runtime_cell import (  # noqa: E402
    allocate_runtime_cell,
    cell_hydrate_lock_path,
    current_cell_id,
    release_runtime_cell,
    runtime_cell_snapshot,
)


@pytest.fixture(autouse=True)
def _clear_cell_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MYRM_DEV_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("MYRM_E2E_CELL_ID", raising=False)
    monkeypatch.delenv("MYRM_E2E_RUN_ID", raising=False)
    monkeypatch.delenv("MYRM_E2E_SHPOIB", raising=False)


def test_allocate_runtime_cell_sets_env() -> None:
    cell = allocate_runtime_cell(run_id="run-a")
    assert cell.cell_id.startswith("cell-")
    assert current_cell_id() == cell.cell_id
    assert os.environ["MYRM_E2E_RUN_ID"] == "run-a"
    assert cell_hydrate_lock_path(cell.cell_id).parent.is_dir()


def test_allocate_runtime_cell_idempotent() -> None:
    first = allocate_runtime_cell(run_id="run-b")
    second = allocate_runtime_cell(run_id="run-c")
    assert second.cell_id == first.cell_id


def test_release_runtime_cell_clears_env() -> None:
    cell = allocate_runtime_cell(run_id="run-d")
    release_runtime_cell(cell.cell_id)
    assert current_cell_id() == ""


def test_runtime_cell_snapshot() -> None:
    cell = allocate_runtime_cell(run_id="run-e")
    snapshot = runtime_cell_snapshot()
    assert snapshot["cellId"] == cell.cell_id
    assert snapshot["runId"] == "run-e"
    assert snapshot["pid"] == os.getpid()
