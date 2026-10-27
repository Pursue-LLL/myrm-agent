"""A truncated ranged read names the file, not the requested range, in its continuation hint."""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.meta_tools.file_ops.core.file_read_handlers import _read_via_service

_HANDLERS = "myrm_agent_harness.agent.meta_tools.file_ops.core.file_read_handlers"
_CONTINUE = re.compile(r"Use (\S+) to continue")
_ROW = re.compile(r"\|row-(\d{5})")
_LAST_ROW = 2400


def _gutter_rows(first: int, last: int) -> str:
    """Rows as ``ResultFormatter`` prints them: absolute line numbers in a gutter."""
    return "\n".join(f"{n:>6}|row-{n:05d} " + "x" * 60 for n in range(first, last + 1))


async def _read(path_str: str, first_row: int) -> str:
    service = MagicMock()
    service.return_value.execute = AsyncMock(return_value=_gutter_rows(first_row, _LAST_ROW))
    with (
        patch(f"{_HANDLERS}.FileOperationService", service),
        patch(f"{_HANDLERS}._dispatch_truncation_event", new_callable=AsyncMock),
    ):
        return await _read_via_service(path_str, None, None, None, config=RunnableConfig())


def _shown_rows(text: str) -> list[int]:
    return [int(n) for n in _ROW.findall(text)]


@pytest.mark.asyncio
async def test_ranged_read_continues_with_a_clean_path_and_the_next_line() -> None:
    text = await _read("doc.md:254-", first_row=254)

    shown = _shown_rows(text)
    assert shown[0] == 254
    assert shown[-1] < _LAST_ROW, "the read must hit the character cap for this test to mean anything"
    hint = _CONTINUE.search(text)
    assert hint is not None
    assert hint.group(1) == f"doc.md:{shown[-1] + 1}-"
    assert "doc.md:254-:" not in text


@pytest.mark.asyncio
async def test_whole_file_read_continues_at_the_next_line() -> None:
    text = await _read("doc.md", first_row=1)

    shown = _shown_rows(text)
    hint = _CONTINUE.search(text)
    assert hint is not None
    assert hint.group(1) == f"doc.md:{shown[-1] + 1}-"


@pytest.mark.asyncio
async def test_bounded_range_continues_without_repeating_either_bound() -> None:
    text = await _read("doc.md:100-2300", first_row=100)

    shown = _shown_rows(text)
    hint = _CONTINUE.search(text)
    assert hint is not None
    assert hint.group(1) == f"doc.md:{shown[-1] + 1}-"
    assert "doc.md:100-2300:" not in text
