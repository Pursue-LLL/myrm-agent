"""A vault read that stops at the character cap names the line to continue from, whole or ranged."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
from myrm_agent_harness.agent.meta_tools.file_ops.utils.vault_read import (
    read_vault_paths_to_parts,
    read_vault_text_content,
)

_RESOLVE_ROOT = "myrm_agent_harness.agent.meta_tools.file_ops.utils.vault_read.resolve_workspace_root"
_DISPATCH = "myrm_agent_harness.utils.event_utils.dispatch_custom_event"
_CONTINUE = re.compile(r"Use (vault://[a-f0-9-]+:\d+-) to continue")
_ROW = re.compile(r"row-(\d{5})")
_ROWS = 3000
_MAX_PAGES = 30


def _put_rows(workspace: str, tail: str = "") -> str:
    body = "".join(f"row-{n:05d}{tail}\n" for n in range(1, _ROWS + 1))
    return ArtifactVault(workspace).put(body, "rows.txt")


async def _read(target: str, workspace: str) -> str:
    with patch(_RESOLVE_ROOT, return_value=workspace), patch(_DISPATCH, new_callable=AsyncMock):
        (part,) = await read_vault_paths_to_parts([target], MagicMock(), "all", config=RunnableConfig())
    return part


async def _page_through(pointer: str, workspace: str) -> tuple[list[int], int]:
    """Follow every continuation hint until the object ends; return the rows seen, in reading order, and the pages."""
    seen: list[int] = []
    target = pointer
    for pages in range(1, _MAX_PAGES + 1):
        page = await _read(target, workspace)
        seen.extend(int(n) for n in _ROW.findall(page))
        hint = _CONTINUE.search(page)
        if hint is None:
            return seen, pages
        target = hint.group(1)
    raise AssertionError(f"still paging after {_MAX_PAGES} pages; last target {target}")


@pytest.mark.asyncio
async def test_ranged_read_continues_at_an_absolute_line(tmp_path: Path) -> None:
    pointer = _put_rows(str(tmp_path))
    page = await _read(f"{pointer}:1000-", str(tmp_path))

    shown = [int(n) for n in _ROW.findall(page)]
    assert shown[0] == 1000
    assert len(shown) < _ROWS - 1000 + 1, "the page must hit the character cap for this test to mean anything"
    hint = _CONTINUE.search(page)
    assert hint is not None
    assert hint.group(1) == f"{pointer}:{shown[-1] + 1}-"
    assert f"{pointer}:1000-:" not in page


@pytest.mark.asyncio
async def test_following_the_hints_reads_every_line_exactly_once(tmp_path: Path) -> None:
    pointer = _put_rows(str(tmp_path))
    seen, pages = await _page_through(pointer, str(tmp_path))
    assert seen == list(range(1, _ROWS + 1))
    assert pages >= 3, "the object must span several pages for this test to mean anything"


@pytest.mark.asyncio
async def test_a_line_separator_inside_a_line_does_not_shift_the_numbers(tmp_path: Path) -> None:
    pointer = _put_rows(str(tmp_path), tail="\u2028tail\x85end")
    seen, _ = await _page_through(pointer, str(tmp_path))
    assert seen == list(range(1, _ROWS + 1))


def test_lines_are_numbered_by_newline_only(tmp_path: Path) -> None:
    pointer = ArtifactVault(str(tmp_path)).put("first\nsecond\u2028still second\nthird", "mixed.txt")
    from myrm_agent_harness.agent.meta_tools.file_ops.core.operation_context import ViewRange

    second = read_vault_text_content(pointer, str(tmp_path), view_range=ViewRange(start=2, end=2))
    assert second == "second\u2028still second\n"
    assert read_vault_text_content(pointer, str(tmp_path), view_range=ViewRange(start=3, end=-1)) == "third"
