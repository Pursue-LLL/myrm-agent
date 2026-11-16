"""Archived context is read under its session and budget guards in every ``file_read_tool`` mode.

A compacted context archive belongs to one session, and a full read of it has a token ceiling; the file service
enforces both. ``preview`` and ``stream`` open a file themselves, so archived context is left to the service: the archive
of another session and one too large for a full read are refused in every mode. These tests send real reads through
``file_read_tool`` with a real ``LocalExecutor`` and a real task budget.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.context_management.infra.session_lock import (
    reset_current_chat_id,
    set_current_chat_id,
)
from myrm_agent_harness.agent.context_management.tracking.task_metrics import (
    clear_task_metrics,
    create_task_metrics,
    get_task_metrics,
)
from myrm_agent_harness.agent.meta_tools.file_ops.core.archive_restore_guard import (
    parse_archive_restore_block_payload,
)
from myrm_agent_harness.agent.meta_tools.file_ops.file_read_tool import create_file_read_tool
from myrm_agent_harness.core.context_vars import workspace_root_var
from myrm_agent_harness.toolkits.code_execution import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import reset_executor, set_executor
from myrm_agent_harness.toolkits.code_execution.executors.local import LocalExecutor

_CHAT = "chat_archive_modes"
_MODES = ["all", "preview", "stream"]
# Far past the ceiling of a full archive read (`MAX_ARCHIVE_FULL_RESTORE_TOKENS`).
_LARGE_ARCHIVE = "\n".join(f"LARGE-ARCHIVE-LINE-{number:04d} " + "x" * 20 for number in range(1, 601)) + "\n"


def _write(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


@dataclass(frozen=True)
class Archives:
    root: Path
    small: str
    large: str
    other_session: str
    evicted_spill: str


@pytest.fixture
def archives(tmp_path: Path) -> Iterator[Archives]:
    root = tmp_path.resolve() / "ws"
    paths = Archives(
        root=root,
        small=f".context/{_CHAT}/compacted/small.txt",
        large=f".context/{_CHAT}/compacted/large.txt",
        other_session=".context/chat_other/compacted/other.txt",
        evicted_spill=f".context/{_CHAT}/evicted/spill.txt",
    )
    contents = {
        paths.small: "SMALL-ARCHIVE-PAYLOAD\n",
        paths.large: _LARGE_ARCHIVE,
        paths.other_session: "OTHER-SESSION-PAYLOAD\n",
        paths.evicted_spill: "EVICTED-SPILL-PAYLOAD\n",
    }
    for relative, content in contents.items():
        _write(root / relative, content)

    executor_token = set_executor(LocalExecutor(ExecutionConfig(), workspace_path=str(root)))
    workspace_token = workspace_root_var.set(str(root))
    chat_token = set_current_chat_id(_CHAT)
    create_task_metrics(_CHAT)
    yield paths
    clear_task_metrics(_CHAT)
    reset_current_chat_id(chat_token)
    workspace_root_var.reset(workspace_token)
    reset_executor(executor_token)


async def _read(path: str, mode: str) -> str:
    tool = create_file_read_tool()
    return str(await tool.ainvoke({"paths": [path], "mode": mode}, config=RunnableConfig()))


def _block_reason(text: str) -> str | None:
    payload = parse_archive_restore_block_payload(text.lstrip())
    return str(payload["reason"]) if payload else None


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", _MODES)
async def test_another_sessions_archive_is_refused_in_every_mode(archives: Archives, mode: str) -> None:
    text = await _read(archives.other_session, mode)

    assert _block_reason(text) == "archive_refetch_session_mismatch"
    assert "OTHER-SESSION-PAYLOAD" not in text


@pytest.mark.skipif(sys.platform == "win32", reason="A directory named C: cannot exist on Windows")
@pytest.mark.asyncio
@pytest.mark.parametrize("mode", _MODES)
async def test_another_sessions_archive_under_a_drive_style_path_is_refused_in_every_mode(
    archives: Archives, mode: str
) -> None:
    """A colon in the path is no reason to open the archive directly: ``C:`` stands in for a drive letter."""
    _write(archives.root / "C:" / archives.other_session, "OTHER-SESSION-PAYLOAD\n")

    text = await _read(f"C:/{archives.other_session}", mode)

    assert _block_reason(text) == "archive_refetch_session_mismatch"
    assert "OTHER-SESSION-PAYLOAD" not in text


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", _MODES)
async def test_an_archive_too_large_for_a_full_read_asks_for_a_range_in_every_mode(
    archives: Archives, mode: str
) -> None:
    text = await _read(archives.large, mode)

    assert _block_reason(text) == "archive_restore_range_required"
    assert "LARGE-ARCHIVE-LINE-0001" not in text
    metrics = get_task_metrics(_CHAT)
    assert metrics is not None
    assert metrics.archive_refetch_tokens == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", _MODES)
async def test_a_range_of_a_large_archive_is_read_in_every_mode(archives: Archives, mode: str) -> None:
    text = await _read(f"{archives.large}:1-3", mode)

    assert "LARGE-ARCHIVE-LINE-0003" in text
    assert "LARGE-ARCHIVE-LINE-0004" not in text


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", _MODES)
async def test_a_small_archive_of_the_session_is_read_in_every_mode(archives: Archives, mode: str) -> None:
    text = await _read(archives.small, mode)

    assert "SMALL-ARCHIVE-PAYLOAD" in text


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["preview", "stream"])
async def test_context_outside_the_archive_directory_is_still_read_directly(archives: Archives, mode: str) -> None:
    text = await _read(archives.evicted_spill, mode)

    assert "EVICTED-SPILL-PAYLOAD" in text
    assert text.startswith("=== ")
