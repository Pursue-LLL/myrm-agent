"""A workbook read as its structure holds no cell values: the result says how to get them.

A large workbook is read as its structure unless the caller asks for more. That view lists sheets, sizes and headers and
nothing else, so a model that wanted a cell has no cue what to call next and falls back to guessing.
"""

from __future__ import annotations

import io
import json

import pytest

from myrm_agent_harness.agent.meta_tools.file_ops.utils import document_reader
from myrm_agent_harness.agent.meta_tools.file_ops.utils.document_reader import read_document_as_text

_NEXT_STEP = "parse_mode='content'"


class _BytesExecutor:
    """The part of CodeExecutor that document_reader uses."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self._files = files

    async def read_file_bytes(self, path: str) -> bytes:
        return self._files[path]


def _workbook(rows: int = 3) -> bytes:
    openpyxl = pytest.importorskip("openpyxl", reason="openpyxl not installed")
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Q3"
    ws.append(["region", "revenue"])
    for i in range(2, rows + 2):
        ws.append([f"region-{i}", 4242 if i == 3 else 100 + i])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def _read(parse_mode: str | None) -> str:
    return await read_document_as_text(
        "data/sales.xlsx", _BytesExecutor({"data/sales.xlsx": _workbook()}), parse_mode=parse_mode
    )


class TestExcelStructureNextStep:
    @pytest.mark.parametrize("parse_mode", [None, "structure"])
    async def test_a_workbook_read_as_structure_says_how_to_read_its_cells(
        self, monkeypatch: pytest.MonkeyPatch, parse_mode: str | None
    ) -> None:
        monkeypatch.setattr(document_reader, "_EXCEL_STRUCTURE_THRESHOLD_BYTES", 1)

        result = await _read(parse_mode)

        assert _NEXT_STEP in result
        assert "4242" not in result

    async def test_the_structure_stays_one_json_line_before_the_next_step(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(document_reader, "_EXCEL_STRUCTURE_THRESHOLD_BYTES", 1)

        header, structure, *rest = (await _read(None)).splitlines()

        assert header == "[Document: data/sales.xlsx]"
        assert json.loads(structure)["sheets"][0]["name"] == "Q3"
        assert _NEXT_STEP in "\n".join(rest)

    @pytest.mark.parametrize("threshold", [1, 10**9], ids=["large-workbook", "small-workbook"])
    async def test_a_read_of_the_cells_has_no_next_step_to_give(
        self, monkeypatch: pytest.MonkeyPatch, threshold: int
    ) -> None:
        monkeypatch.setattr(document_reader, "_EXCEL_STRUCTURE_THRESHOLD_BYTES", threshold)

        result = await _read("content")

        assert "4242" in result
        assert _NEXT_STEP not in result

    async def test_a_small_workbook_is_read_in_full_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(document_reader, "_EXCEL_STRUCTURE_THRESHOLD_BYTES", 10**9)

        result = await _read(None)

        assert "4242" in result
        assert _NEXT_STEP not in result

    async def test_the_audit_is_not_given_a_next_step(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(document_reader, "_EXCEL_STRUCTURE_THRESHOLD_BYTES", 1)

        assert _NEXT_STEP not in await _read("audit")
