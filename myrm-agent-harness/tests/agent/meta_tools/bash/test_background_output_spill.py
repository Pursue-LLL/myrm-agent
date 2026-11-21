"""The log of a background job: when it is created, what it holds, how it ends and what a failure costs."""

from __future__ import annotations

import asyncio
import random
from pathlib import Path

import pytest

import myrm_agent_harness.agent.meta_tools.bash._background.output_spill as spill_module
from myrm_agent_harness.agent.context_management.infra.evicted import (
    EVICTED_BASENAME_PATTERN,
    read_evicted_file_meta,
)
from myrm_agent_harness.agent.meta_tools.bash._background.output_spill import BackgroundOutputSpillWriter
from myrm_agent_harness.agent.meta_tools.bash._background.output_window import cap_window
from myrm_agent_harness.agent.meta_tools.bash._background.types import OUTPUT_RING_LINES
from myrm_agent_harness.core.context_vars import workspace_root_var


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / ".context" / "chat-1" / "evicted" / "output_0a1b2c3d.txt"


def _write(writer: BackgroundOutputSpillWriter, count: int, *, start: int = 0, stream: str = "stdout") -> None:
    for number in range(start, start + count):
        writer.append_line(stream, f"line-{number}")


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def test_a_job_below_the_threshold_leaves_no_file(log_path: Path) -> None:
    writer = BackgroundOutputSpillWriter(job_id="job", path=log_path)

    _write(writer, 79)
    writer.close()

    assert writer.vault_log_ref is None
    assert not log_path.parent.exists()


def test_the_file_starts_at_the_first_line_once_the_threshold_is_reached(log_path: Path) -> None:
    writer = BackgroundOutputSpillWriter(job_id="job", path=log_path)

    _write(writer, 80)

    assert writer.vault_log_ref == log_path.name
    assert EVICTED_BASENAME_PATTERN.match(log_path.name)
    assert _lines(log_path) == [f"line-{n}" for n in range(80)]


def test_a_stderr_line_carries_its_stream_and_empty_lines_are_kept(log_path: Path) -> None:
    writer = BackgroundOutputSpillWriter(job_id="job", path=log_path)

    _write(writer, 78)
    writer.append_line("stderr", "warn")
    writer.append_line("stdout", "")
    writer.close()

    assert _lines(log_path)[-2:] == ["[stderr] warn", ""]


def test_long_lines_create_the_file_before_the_threshold(log_path: Path) -> None:
    """A read shows 64 Ki characters at most: output that a read would cut must already be in a file."""
    writer = BackgroundOutputSpillWriter(job_id="job", path=log_path)

    for number in range(10):
        writer.append_line("stdout", f"{number}" + "x" * 7_000)

    assert writer.vault_log_ref == log_path.name
    assert len(_lines(log_path)) == 10


def test_waiting_lines_are_written_in_batches_and_the_tail_at_close(log_path: Path) -> None:
    writer = BackgroundOutputSpillWriter(job_id="job", path=log_path)
    _write(writer, 80)

    _write(writer, 100, start=80)
    assert len(_lines(log_path)) == 80

    _write(writer, 28, start=180)  # the 128th waiting line forces a write
    assert len(_lines(log_path)) == 208

    _write(writer, 5, start=208)
    writer.close()
    assert _lines(log_path) == [f"line-{n}" for n in range(213)]


@pytest.mark.asyncio
async def test_waiting_lines_are_written_within_the_interval_even_when_the_job_goes_quiet(
    log_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(spill_module, "_FLUSH_INTERVAL_SECONDS", 0.02)
    writer = BackgroundOutputSpillWriter(job_id="job", path=log_path)
    _write(writer, 85)

    await asyncio.sleep(0.2)

    assert len(_lines(log_path)) == 85
    writer.close()


def test_what_waits_for_a_write_is_always_inside_what_a_read_shows(log_path: Path) -> None:
    """A read that reports dropped lines sends the model to the log; every line the log lacks must be in that read."""
    rng = random.Random(7)
    writer = BackgroundOutputSpillWriter(job_id="job", path=log_path)
    printed: list[str] = []
    for number in range(600):
        text = f"{number} " + "y" * rng.choice((1, 20, 400, 3_000, 8_000))
        printed.append(text)
        writer.append_line("stdout", text)
        in_file = len(_lines(log_path)) if log_path.exists() else 0
        window, _ = cap_window(printed[-OUTPUT_RING_LINES:])
        assert len(printed) - in_file <= len(window), number
    writer.close()
    assert len(_lines(log_path)) == len(printed)


def test_the_file_is_capped_and_ends_with_the_marker_the_reader_recognises(
    log_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(spill_module, "MAX_STORED_CHARS", 2_000)
    writer = BackgroundOutputSpillWriter(job_id="job", path=log_path)
    total = 0
    for number in range(300):
        text = f"{number:04d} " + "z" * 60
        writer.append_line("stdout", text)
        total += len(text) + 1
    writer.close()

    meta = read_evicted_file_meta(log_path)
    assert meta.storage_truncated is True
    assert meta.original_chars == total
    assert log_path.read_text(encoding="utf-8").startswith("0000 ")
    assert log_path.stat().st_size < 2_000 + 200  # the cap plus the marker


def test_a_file_that_is_not_capped_has_no_marker(log_path: Path) -> None:
    writer = BackgroundOutputSpillWriter(job_id="job", path=log_path)
    _write(writer, 100)
    writer.close()

    assert read_evicted_file_meta(log_path).storage_truncated is False


def test_a_directory_that_cannot_be_created_closes_the_log_and_nothing_else(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("a file where the directory would go")
    writer = BackgroundOutputSpillWriter(job_id="job", path=blocker / "evicted" / "output_0a1b2c3d.txt")

    _write(writer, 200)
    writer.close()

    assert writer.vault_log_ref is None


def test_a_failed_write_stops_the_log_and_keeps_what_was_written(
    log_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    writer = BackgroundOutputSpillWriter(job_id="job", path=log_path)
    _write(writer, 80)

    def full_disk(_text: str) -> int:
        raise OSError("no space left on device")

    monkeypatch.setattr(writer._file, "write", full_disk)
    _write(writer, 200, start=80)
    writer.close()

    assert writer.vault_log_ref == log_path.name
    assert _lines(log_path) == [f"line-{n}" for n in range(80)]


def test_an_existing_file_is_never_overwritten(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True)
    log_path.write_text("someone else's log\n", encoding="utf-8")
    writer = BackgroundOutputSpillWriter(job_id="job", path=log_path)

    _write(writer, 200)
    writer.close()

    assert writer.vault_log_ref is None
    assert log_path.read_text(encoding="utf-8") == "someone else's log\n"


def test_lines_after_close_are_ignored_and_close_is_idempotent(log_path: Path) -> None:
    writer = BackgroundOutputSpillWriter(job_id="job", path=log_path)
    _write(writer, 90)
    writer.close()

    _write(writer, 50, start=90)
    writer.close()

    assert len(_lines(log_path)) == 90


def test_the_writer_serves_the_chat_and_workspace_the_foreground_evicted_files_use(tmp_path: Path) -> None:
    token = workspace_root_var.set(str(tmp_path))
    try:
        writer = BackgroundOutputSpillWriter.for_session(session_id="chat_abc", job_id="job")
        no_session = BackgroundOutputSpillWriter.for_session(session_id=None, job_id="job")
    finally:
        workspace_root_var.reset(token)

    assert no_session is None
    assert writer is not None
    _write(writer, 80)
    created = list((tmp_path / ".context" / "abc" / "evicted").glob("output_*.txt"))
    assert [path.name for path in created] == [writer.vault_log_ref]


def test_without_a_workspace_there_is_no_writer() -> None:
    assert workspace_root_var.get() == ""
    assert BackgroundOutputSpillWriter.for_session(session_id="chat_abc", job_id="job") is None
