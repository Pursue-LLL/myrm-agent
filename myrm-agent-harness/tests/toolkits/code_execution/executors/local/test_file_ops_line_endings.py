"""``LocalExecutor`` reads and writes file text exactly as stored: it never rewrites a line ending.

Text-mode I/O translates line endings: on read ``\\r\\n`` and a lone ``\\r`` become ``\\n``, and on write ``\\n`` becomes
``\\r\\n`` on Windows (so the write side only shows on that platform). Every file tool reads and writes through
``read_file`` / ``write_file``, so a CRLF file reached the edit pipeline as LF text, and an edit wrote it back as LF.
"""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.local.executor import LocalExecutor

_STORED = {
    "lf": b"alpha\nbeta\n",
    "crlf": b"alpha\r\nbeta\r\n",
    "mixed": b"alpha\r\nbeta\ngamma\r\n",
    "lone_cr": b"alpha\rbeta\r",
    "no_final_newline": b"alpha\r\nbeta",
    "unicode_crlf": "héllo\r\n世界\r\n".encode(),
}
_CASES = pytest.mark.parametrize("stored", _STORED.values(), ids=_STORED.keys())


@pytest.fixture
def executor(tmp_path: Path) -> LocalExecutor:
    local = LocalExecutor(ExecutionConfig())
    local.bind_workspace(str(tmp_path))
    return local


@_CASES
async def test_read_file_returns_the_stored_text_untranslated(
    executor: LocalExecutor, tmp_path: Path, stored: bytes
) -> None:
    (tmp_path / "f.txt").write_bytes(stored)

    assert await executor.read_file("f.txt") == stored.decode("utf-8")


@_CASES
async def test_write_file_stores_the_given_text_untranslated(
    executor: LocalExecutor, tmp_path: Path, stored: bytes
) -> None:
    await executor.write_file("f.txt", stored.decode("utf-8"))

    assert (tmp_path / "f.txt").read_bytes() == stored


@_CASES
async def test_a_read_then_write_leaves_the_file_byte_identical(
    executor: LocalExecutor, tmp_path: Path, stored: bytes
) -> None:
    (tmp_path / "f.txt").write_bytes(stored)

    await executor.write_file("copy.txt", await executor.read_file("f.txt"))

    assert (tmp_path / "copy.txt").read_bytes() == stored


async def test_a_gzipped_file_is_read_untranslated_too(executor: LocalExecutor, tmp_path: Path) -> None:
    (tmp_path / "f.txt.gz").write_bytes(gzip.compress(_STORED["crlf"]))

    assert await executor.read_file("f.txt.gz") == _STORED["crlf"].decode("utf-8")
