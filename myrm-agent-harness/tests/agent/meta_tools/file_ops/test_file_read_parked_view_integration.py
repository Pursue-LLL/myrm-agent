"""A long paste the context guard parked is read back through the real file_read_tool in few calls.

Parks real files with the real spillover engine and reads them with the real tool, following the continuation
hint the way the model does. The contract: a parked text is paged by o200k tokens and a long line is split into
rows, so the last character of any paste is reachable; every other file keeps the code-file read caps.

Run under the harness monorepo via ``./myrm test -m integration``.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.config import DEFAULT_FILE_IO_CONFIG
from myrm_agent_harness.agent.context_guard import KEPT_SPILLOVER_DIR, ContextGuardConfig, SpilloverEngine
from myrm_agent_harness.agent.meta_tools.file_ops.core.parked_file_view import PAGE_TOKEN_BUDGET
from myrm_agent_harness.agent.meta_tools.file_ops.file_read_tool import create_file_read_tool
from myrm_agent_harness.core.context_vars import chat_id_var, workspace_root_var
from myrm_agent_harness.toolkits.code_execution import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import reset_executor, set_executor
from myrm_agent_harness.toolkits.code_execution.executors.local import LocalExecutor
from myrm_agent_harness.toolkits.code_execution.utils.workspace_path import WorkspacePathResolver
from myrm_agent_harness.utils.text_utils import get_token_count

_CHAT_ID = "chat-parked-view"
_CONTINUE_HINT = re.compile(r"Use (\S+?:\d+-) to continue")
_END_MARKER = "END_OF_THE_PASTE"
# A page may overshoot its budget by a tenth, and carries a continuation hint of a few dozen tokens.
_PAGE_CEILING = PAGE_TOKEN_BUDGET * 110 // 100 + 300
_CLAUSE = (
    "Section {n}. The supplier shall deliver the goods within thirty days of the purchase order. Late delivery "
    "incurs a penalty of 0.5% per day, capped at 10% of the order value.\n"
)


@pytest.fixture
def workspace(tmp_path: Path) -> Iterator[str]:
    ws = str(tmp_path)
    WorkspacePathResolver._cached_workspace_root = None
    os.environ["WORKSPACE_ROOT"] = ws
    yield ws
    os.environ.pop("WORKSPACE_ROOT", None)
    WorkspacePathResolver._cached_workspace_root = None


@contextmanager
def _session(ws: str) -> Iterator[None]:
    executor_token = set_executor(LocalExecutor(ExecutionConfig(), workspace_path=ws))
    chat_token = chat_id_var.set(_CHAT_ID)
    workspace_token = workspace_root_var.set(ws)
    try:
        yield
    finally:
        workspace_root_var.reset(workspace_token)
        chat_id_var.reset(chat_token)
        reset_executor(executor_token)


def _park(ws: str, text: str) -> str:
    """Park *text* the way the server parks a user's paste and return the path the stub names."""
    parked = SpilloverEngine(
        ContextGuardConfig(max_message_chars=100, spillover_dir_name=KEPT_SPILLOVER_DIR)
    ).process_content(text, base_dir=ws)
    assert parked.payload is not None
    return parked.payload.relative_path


async def _read_pages(path: str, *, mode: str = "all") -> list[str]:
    """Read *path* with the Fast-track tool, following the continuation hint until the text ends."""
    tool = create_file_read_tool(path_policy="evicted_uploaded")
    config = RunnableConfig(configurable={"context": {"chat_id": _CHAT_ID}})
    pages: list[str] = []
    target = path
    while len(pages) < 40:
        page = await tool.ainvoke({"paths": [target], "mode": mode}, config=config)
        assert isinstance(page, str)
        pages.append(page)
        hint = _CONTINUE_HINT.search(page)
        if hint is None:
            return pages
        target = hint.group(1)
    raise AssertionError("the continuation hint never ended")


def _prose(chars: int) -> str:
    return "".join(_CLAUSE.format(n=n) for n in range(chars // 60))[:chars] + f"\n{_END_MARKER}"


def _one_line_json(chars: int) -> str:
    items = [{"id": n, "name": f"item-{n}", "tags": ["a", "b", "c"], "note": "x" * 20} for n in range(2000)]
    return json.dumps({"items": items}, separators=(",", ":"))[:chars] + _END_MARKER


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_paste_that_fits_a_page_is_read_back_in_one_call(workspace: str) -> None:
    path = _park(workspace, _prose(70_000))
    with _session(workspace):
        pages = await _read_pages(path)
    assert len(pages) == 1
    assert _END_MARKER in pages[0]
    assert get_token_count(pages[0]) <= _PAGE_CEILING


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_paste_of_several_pages_is_read_back_in_filled_pages(workspace: str) -> None:
    path = _park(workspace, _prose(300_000))
    with _session(workspace):
        pages = await _read_pages(path)
    assert 2 <= len(pages) <= 5
    assert _END_MARKER in pages[-1]
    assert all(get_token_count(page) <= _PAGE_CEILING for page in pages)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_the_absolute_path_of_a_paste_is_read_back_the_same_way(workspace: str) -> None:
    path = _park(workspace, _prose(70_000))
    with _session(workspace):
        pages = await _read_pages(str(Path(workspace) / path))
    assert len(pages) == 1
    assert _END_MARKER in pages[0]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_paste_without_a_line_break_is_read_back_to_its_last_character(workspace: str) -> None:
    path = _park(workspace, _one_line_json(64_500))
    with _session(workspace):
        pages = await _read_pages(path)
    assert _END_MARKER in pages[-1]
    assert "split into rows" in pages[0]
    assert "... [truncated]" not in "".join(pages)
    assert all(get_token_count(page) <= _PAGE_CEILING for page in pages)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_secret_on_a_row_boundary_of_a_wrapped_paste_is_masked(workspace: str) -> None:
    secret = "ghp_Ab3dE6gH9jK2mN5pQ8sT1vW4yZ7bC0eF3hJ6"
    text = "a" * 1981 + f" {secret} " + "b" * 63_000 + _END_MARKER
    path = _park(workspace, text)
    with _session(workspace):
        pages = await _read_pages(path)
    shown = "".join(pages)
    assert _END_MARKER in pages[-1]
    assert secret[8:30] not in shown
    assert secret[:20] not in shown
    assert "ghp_Ab...3hJ6" in re.sub(r"\n *\d+\|", "", shown)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_range_of_a_wrapped_paste_shows_the_rows_the_whole_read_numbers(workspace: str) -> None:
    path = _park(workspace, _one_line_json(64_500))
    with _session(workspace):
        whole = (await _read_pages(path))[0]
        ranged = (await _read_pages(f"{path}:31-32"))[0]
    row = re.compile(r"^ *(?:31|32)\|.*$", re.MULTILINE)
    assert row.findall(ranged)
    assert row.findall(ranged) == row.findall(whole)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["preview", "stream"])
async def test_preview_and_stream_read_a_paste_as_pages_too(workspace: str, mode: str) -> None:
    path = _park(workspace, _one_line_json(64_500))
    with _session(workspace):
        pages = await _read_pages(path, mode=mode)
    assert _END_MARKER in pages[-1]
    assert "(preview mode)" not in pages[0]
    assert "split into rows" in pages[0]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_any_other_file_keeps_the_code_file_read_caps(workspace: str) -> None:
    notes = Path(workspace) / "docs" / "notes.md"
    notes.parent.mkdir()
    notes.write_text(_prose(70_000), encoding="utf-8")
    minified = Path(workspace) / "app.min.js"
    minified.write_text("head\n" + "x" * 5000 + "\ntail\n", encoding="utf-8")
    with _session(workspace):
        tool = create_file_read_tool()
        capped = await tool.ainvoke({"paths": ["docs/notes.md"], "mode": "all"}, config=RunnableConfig())
        clamped = await tool.ainvoke({"paths": ["app.min.js"], "mode": "all"}, config=RunnableConfig())
    assert isinstance(capped, str)
    assert isinstance(clamped, str)
    assert f"Output capped at {DEFAULT_FILE_IO_CONFIG.max_read_chars:,} chars" in capped
    assert _END_MARKER not in capped
    assert "... [truncated]" in clamped
    assert "split into rows" not in clamped
    assert "x" * 2001 not in clamped
