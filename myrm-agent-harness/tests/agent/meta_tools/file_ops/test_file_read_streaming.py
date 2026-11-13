"""Tests for the chunked and preview readers behind file_read's ``stream`` and ``preview`` modes.

Coverage:
1. ``read_file_preview``: first lines plus a hint to read on, short and empty files, undecodable bytes.
2. ``read_file_chunked``: whole-file read across several chunks, the one-character-past-the-cap contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from myrm_agent_harness.agent.meta_tools.file_ops import streaming
from myrm_agent_harness.agent.meta_tools.file_ops.streaming import read_file_chunked, read_file_preview


def _write_lines(path: Path, count: int) -> str:
    text = "".join(f"Line {i}: {'x' * 90}\n" for i in range(1, count + 1))
    path.write_text(text, encoding="utf-8")
    return text


@pytest.mark.asyncio
async def test_preview_returns_first_lines_and_a_hint_to_read_on(tmp_path: Path) -> None:
    path = tmp_path / "big.txt"
    _write_lines(path, 2000)

    result = await read_file_preview(path, max_lines=1000)

    assert "Line 1:" in result
    assert "Line 1000:" in result
    assert "Line 1001:" not in result
    assert "file continues" in result
    assert "Tip" in result


@pytest.mark.asyncio
async def test_preview_returns_a_short_file_whole_without_a_hint(tmp_path: Path) -> None:
    path = tmp_path / "short.txt"
    path.write_text("one\ntwo\nthree\n", encoding="utf-8")

    assert await read_file_preview(path, max_lines=1000) == "one\ntwo\nthree"


@pytest.mark.asyncio
async def test_preview_of_an_empty_file_is_empty(tmp_path: Path) -> None:
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")

    assert await read_file_preview(path) == ""


@pytest.mark.asyncio
async def test_undecodable_bytes_become_replacement_characters(tmp_path: Path) -> None:
    path = tmp_path / "binaryish.txt"
    path.write_bytes(b"ok \xff\xfe end\n")

    assert await read_file_chunked(path) == "ok \ufffd\ufffd end\n"
    assert await read_file_preview(path) == "ok \ufffd\ufffd end"


@pytest.mark.asyncio
async def test_chunked_read_joins_every_chunk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "multi.txt"
    text = _write_lines(path, 500)
    monkeypatch.setattr(streaming, "_CHUNK_CHARS", 1000)

    assert len(text) > 10 * 1000
    assert await read_file_chunked(path) == text


@pytest.mark.asyncio
async def test_chunked_read_with_a_cap_stops_one_character_past_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cap is larger than a chunk, so the reader must not finish the chunk that crosses it."""
    path = tmp_path / "multi.txt"
    text = _write_lines(path, 500)
    monkeypatch.setattr(streaming, "_CHUNK_CHARS", 100)

    assert await read_file_chunked(path, max_chars=250) == text[:251]


@pytest.mark.asyncio
async def test_chunked_read_with_a_cap_beyond_the_file_returns_everything(tmp_path: Path) -> None:
    path = tmp_path / "small.txt"
    text = _write_lines(path, 10)

    assert await read_file_chunked(path, max_chars=len(text) + 5000) == text
