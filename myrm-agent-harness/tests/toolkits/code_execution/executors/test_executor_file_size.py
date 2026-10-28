"""``file_size`` measures a regular file without reading it, and ``.gz`` reads cannot exhaust memory.

The base-class default (shell) and the real ``LocalExecutor`` (stat) must agree, so both run the same cases.
A FIFO is the sharpest probe: opening one for reading blocks forever, so any implementation that reads the
file to learn its size would hang the test instead of failing it.
"""

import asyncio
import gzip
import io
import os
import tracemalloc
from collections.abc import Awaitable
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import CodeExecutor
from myrm_agent_harness.toolkits.code_execution.executors.gunzip import MAX_GUNZIP_BYTES, gunzip_bounded
from myrm_agent_harness.toolkits.code_execution.executors.local.executor import LocalExecutor
from myrm_agent_harness.toolkits.code_execution.executors.middleware import CodeExecutorMiddleware
from tests.toolkits.code_execution._executor_stub import InProcessExecutor


async def _promptly[T](awaitable: Awaitable[T]) -> T:
    """A hang is a failure here, not a stuck test run."""
    return await asyncio.wait_for(awaitable, timeout=10)


@pytest.fixture(params=["shell-default", "local-stat"])
def executor(request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CodeExecutor:
    monkeypatch.chdir(tmp_path)
    ex: CodeExecutor = InProcessExecutor() if request.param == "shell-default" else LocalExecutor(ExecutionConfig())
    ex.bind_workspace(str(tmp_path))
    return ex


@pytest.mark.asyncio
async def test_size_of_a_regular_file_is_its_byte_length(executor: CodeExecutor, tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("héllo", encoding="utf-8")  # 6 bytes, 5 characters
    (tmp_path / "empty.txt").write_bytes(b"")
    (tmp_path / "blob.bin").write_bytes(bytes(range(256)) * 4)

    assert await _promptly(executor.file_size("a.txt")) == 6
    assert await _promptly(executor.file_size("empty.txt")) == 0
    assert await _promptly(executor.file_size("blob.bin")) == 1024


@pytest.mark.asyncio
async def test_a_missing_file_is_not_found(executor: CodeExecutor) -> None:
    with pytest.raises(FileNotFoundError):
        await _promptly(executor.file_size("nope.txt"))


@pytest.mark.asyncio
async def test_a_directory_has_no_file_size(executor: CodeExecutor, tmp_path: Path) -> None:
    (tmp_path / "d").mkdir()
    with pytest.raises(OSError, match="Not a regular file"):
        await _promptly(executor.file_size("d"))


@pytest.mark.asyncio
@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs POSIX FIFOs")
async def test_a_fifo_is_refused_instead_of_blocking(executor: CodeExecutor, tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "pipe")
    (tmp_path / "link").symlink_to(tmp_path / "pipe")
    for name in ("pipe", "link"):
        with pytest.raises(OSError, match="Not a regular file"):
            await _promptly(executor.file_size(name))


@pytest.mark.asyncio
async def test_a_path_outside_the_workspace_is_refused(executor: CodeExecutor) -> None:
    with pytest.raises(ValueError, match="Path traversal detected"):
        await _promptly(executor.file_size("../outside.txt"))


@pytest.mark.asyncio
async def test_the_middleware_forwards_file_size(tmp_path: Path) -> None:
    inner = LocalExecutor(ExecutionConfig())
    inner.bind_workspace(str(tmp_path))
    (tmp_path / "a.txt").write_text("12345")
    assert await CodeExecutorMiddleware(inner).file_size("a.txt") == 5


class TestBoundedGunzip:
    def test_round_trip_including_concatenated_members(self) -> None:
        data = gzip.compress(b"hello ") + gzip.compress(b"world")
        assert gunzip_bounded(data) == b"hello world"

    def test_output_over_the_limit_is_refused(self) -> None:
        with pytest.raises(ValueError, match="exceeds"):
            gunzip_bounded(gzip.compress(b"x" * 1001), limit=1000)
        assert gunzip_bounded(gzip.compress(b"x" * 1000), limit=1000) == b"x" * 1000

    def test_memory_stays_bounded_whatever_the_compression_ratio(self) -> None:
        buffer = io.BytesIO()
        with gzip.GzipFile(fileobj=buffer, mode="wb") as writer:
            for _ in range(50):
                writer.write(b"\0" * (1024 * 1024))
        bomb = buffer.getvalue()  # ~50 MB of zeros in ~50 KB
        assert len(bomb) < 1024 * 1024

        tracemalloc.start()
        try:
            with pytest.raises(ValueError, match="exceeds"):
                gunzip_bounded(bomb, limit=1024 * 1024)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        assert peak < 8 * 1024 * 1024

    def test_data_that_is_not_gzip_is_an_os_error(self) -> None:
        with pytest.raises(OSError):
            gunzip_bounded(b"definitely not gzip")


@pytest.mark.asyncio
async def test_read_file_decompresses_gz_and_refuses_a_bomb(executor: CodeExecutor, tmp_path: Path) -> None:
    (tmp_path / "log.txt.gz").write_bytes(gzip.compress("héllo".encode()))
    assert await _promptly(executor.read_file("log.txt.gz")) == "héllo"

    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb") as writer:
        chunk = b"\0" * (1024 * 1024)
        for _ in range((MAX_GUNZIP_BYTES // len(chunk)) + 2):
            writer.write(chunk)
    (tmp_path / "bomb.txt.gz").write_bytes(buffer.getvalue())
    with pytest.raises(ValueError, match="exceeds"):
        await _promptly(executor.read_file("bomb.txt.gz"))
