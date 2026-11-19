"""A persistent bash session starts in its work directory whatever the folder's name holds.

The session writes ``cd <work_dir>`` into the shell it starts, so the shell must read the name as one word: a quote
character in it must not end the quoting early, and what follows it must not run.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.code_execution.session import LocalPersistentSession
from tests.toolkits.code_execution._session_helpers import make_config

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(sys.platform == "win32", reason="the work directory is quoted for bash"),
]

_FOLDER_NAMES = ["My Docs", "project (1)", "R&D", "dollar$HOME", "John's Docs", "'", "a'b'c"]


@pytest.mark.parametrize("name", _FOLDER_NAMES)
async def test_the_shell_starts_in_the_work_directory(tmp_path: Path, name: str) -> None:
    work_dir = tmp_path / name
    work_dir.mkdir()
    session = LocalPersistentSession(make_config(timeout=5, work_dir=str(work_dir)))
    await session.start()
    try:
        result = await session.execute("pwd")
        assert result.stdout.strip() == str(work_dir)
    finally:
        await session.close()


async def test_a_folder_name_is_never_run_as_a_command(tmp_path: Path) -> None:
    work_dir = tmp_path / "x'; touch MARK; '"
    work_dir.mkdir()
    session = LocalPersistentSession(make_config(timeout=5, work_dir=str(work_dir)))
    await session.start()
    try:
        await session.execute("pwd")
    finally:
        await session.close()

    assert not (work_dir / "MARK").exists()
