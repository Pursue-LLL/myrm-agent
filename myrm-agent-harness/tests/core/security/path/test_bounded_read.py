"""Tests for the bounded text reader: a read that never takes more than a budget of characters or blocks on a special file.

[INPUT]
- core.security.path::read_text_bounded, ReadRefusal (POS: the primitive under test, imported through the package facade)

[OUTPUT]
- Fails when the reader returns text that ``Path.read_text`` would not return for the same regular file, reads more than
  ``max_chars + 1`` characters, opens a FIFO or device and waits on it, or follows a link out of the boundary it was given.

[POS]
Unit contract of the primitive that the workspace-rule scan, the workspace skill scan and the pre-trust manifest read
through. The special-file cases run against real FIFOs and ``/dev/zero`` with a deadline, so a regression fails instead of
hanging the run.
"""

from __future__ import annotations

import os
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import pytest

from myrm_agent_harness.core.security.path import ReadRefusal, read_text_bounded
from tests.support.read_spy import record_read_sizes

POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="FIFOs, device nodes and sparse files are POSIX")


@pytest.fixture
def read_sizes(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """The size argument of every ``read`` the primitive makes."""
    return record_read_sizes(monkeypatch)


def _within_deadline(call: Callable[[], object], seconds: float = 5.0) -> object:
    """Run *call* on a thread and fail instead of hanging when it does not return in *seconds*."""
    outcome: list[object] = []
    worker = threading.Thread(target=lambda: outcome.append(call()), daemon=True)
    worker.start()
    worker.join(seconds)
    assert not worker.is_alive(), "the read blocked on a special file"
    return outcome[0]


class TestRegularFiles:
    @pytest.mark.parametrize("errors", ["strict", "replace"])
    @pytest.mark.parametrize(
        "payload", [b"plain\n", b"crlf\r\nline\r\n", b"lone\rcr", "ünïcode \u4e2d\u6587".encode(), b""]
    )
    def test_the_text_is_what_read_text_returns(
        self, tmp_path: Path, payload: bytes, errors: Literal["strict", "replace"]
    ) -> None:
        path = tmp_path / "f.txt"
        path.write_bytes(payload)

        result = read_text_bounded(path, 1000, errors=errors)

        assert result.refusal is None
        assert result.text == path.read_text(encoding="utf-8", errors=errors)

    def test_invalid_utf8_raises_by_default_like_read_text(self, tmp_path: Path) -> None:
        path = tmp_path / "f.txt"
        path.write_bytes(b"ok \xff\xfe broken")

        with pytest.raises(UnicodeDecodeError):
            read_text_bounded(path, 1000)

    def test_invalid_utf8_becomes_replacement_characters_when_asked(self, tmp_path: Path) -> None:
        path = tmp_path / "f.txt"
        path.write_bytes(b"ok \xff\xfe broken")

        assert read_text_bounded(path, 1000, errors="replace").text == "ok \ufffd\ufffd broken"

    def test_the_characters_read_are_reported(self, tmp_path: Path) -> None:
        path = tmp_path / "f.txt"
        path.write_text("héllo", encoding="utf-8")

        assert read_text_bounded(path, 1000).chars_read == 5

    def test_a_file_of_exactly_the_limit_is_returned(self, tmp_path: Path) -> None:
        path = tmp_path / "f.txt"
        path.write_text("a" * 10, encoding="utf-8")

        result = read_text_bounded(path, 10)

        assert (result.text, result.refusal) == ("a" * 10, None)

    def test_a_file_one_character_over_the_limit_is_refused_and_charged_one_past_it(self, tmp_path: Path) -> None:
        path = tmp_path / "f.txt"
        path.write_text("a" * 11, encoding="utf-8")

        result = read_text_bounded(path, 10)

        assert (result.text, result.refusal, result.chars_read) == (None, ReadRefusal.TOO_LARGE, 11)

    def test_a_large_file_is_read_with_a_single_bounded_read(self, tmp_path: Path, read_sizes: list[int]) -> None:
        path = tmp_path / "f.txt"
        path.write_text("a" * 5_000_000, encoding="utf-8")

        result = read_text_bounded(path, 100)

        assert result.refusal is ReadRefusal.TOO_LARGE
        assert read_sizes == [101]

    def test_a_missing_file_raises_like_read_text(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            read_text_bounded(tmp_path / "absent.txt", 10)

    def test_a_symlink_to_a_regular_file_is_followed(self, tmp_path: Path) -> None:
        target = tmp_path / "target.txt"
        target.write_text("linked", encoding="utf-8")
        link = tmp_path / "link.txt"
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("symlinks are not available")

        assert read_text_bounded(link, 100).text == "linked"


class TestKindOfFile:
    def test_a_directory_is_refused_as_not_a_regular_file(self, tmp_path: Path) -> None:
        if sys.platform == "win32":
            with pytest.raises(PermissionError):
                read_text_bounded(tmp_path, 10)
            return

        result = read_text_bounded(tmp_path, 10)

        assert (result.text, result.refusal, result.chars_read) == (None, ReadRefusal.NOT_A_REGULAR_FILE, 0)

    @POSIX_ONLY
    def test_a_fifo_is_refused_without_waiting_for_a_writer(self, tmp_path: Path) -> None:
        fifo = tmp_path / "pipe"
        os.mkfifo(fifo)

        result = _within_deadline(lambda: read_text_bounded(fifo, 10))

        assert result.refusal is ReadRefusal.NOT_A_REGULAR_FILE  # type: ignore[attr-defined]

    @POSIX_ONLY
    def test_a_symlink_to_a_fifo_is_refused_without_waiting(self, tmp_path: Path) -> None:
        fifo = tmp_path / "pipe"
        os.mkfifo(fifo)
        link = tmp_path / "link"
        link.symlink_to(fifo)

        result = _within_deadline(lambda: read_text_bounded(link, 10))

        assert result.refusal is ReadRefusal.NOT_A_REGULAR_FILE  # type: ignore[attr-defined]

    @POSIX_ONLY
    def test_a_symlink_to_an_endless_device_is_refused_unread(self, tmp_path: Path, read_sizes: list[int]) -> None:
        link = tmp_path / "zero"
        link.symlink_to("/dev/zero")

        result = _within_deadline(lambda: read_text_bounded(link, 10))

        assert result.refusal is ReadRefusal.NOT_A_REGULAR_FILE  # type: ignore[attr-defined]
        assert read_sizes == []

    @POSIX_ONLY
    def test_the_descriptor_is_closed_when_the_kind_cannot_be_read(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "f.txt"
        path.write_text("x", encoding="utf-8")

        def failing_fstat(fd: int) -> os.stat_result:
            raise OSError("stat failed")

        monkeypatch.setattr(os, "fstat", failing_fstat)
        before = len(os.listdir("/dev/fd"))

        for _ in range(50):
            with pytest.raises(OSError, match="stat failed"):
                read_text_bounded(path, 10)

        assert len(os.listdir("/dev/fd")) <= before + 1

    @POSIX_ONLY
    def test_the_descriptor_is_closed_when_the_kind_is_refused(self, tmp_path: Path) -> None:
        fifo = tmp_path / "pipe"
        os.mkfifo(fifo)
        before = len(os.listdir("/dev/fd"))

        for _ in range(50):
            read_text_bounded(fifo, 10)

        assert len(os.listdir("/dev/fd")) <= before + 1


class TestBoundary:
    def test_a_file_inside_the_boundary_is_read(self, tmp_path: Path) -> None:
        (tmp_path / "in.txt").write_text("inside", encoding="utf-8")

        assert read_text_bounded(tmp_path / "in.txt", 100, boundary=tmp_path).text == "inside"

    def test_a_link_out_of_the_boundary_is_refused_unread(self, tmp_path: Path, read_sizes: list[int]) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        secret = tmp_path / "secret.txt"
        secret.write_text("outside", encoding="utf-8")
        link = workspace / "link.txt"
        try:
            link.symlink_to(secret)
        except OSError:
            pytest.skip("symlinks are not available")

        result = read_text_bounded(link, 100, boundary=workspace)

        assert (result.text, result.refusal, result.chars_read) == (None, ReadRefusal.OUTSIDE_BOUNDARY, 0)
        assert read_sizes == []

    def test_the_same_link_is_followed_when_no_boundary_is_given(self, tmp_path: Path) -> None:
        secret = tmp_path / "secret.txt"
        secret.write_text("outside", encoding="utf-8")
        link = tmp_path / "workspace-link.txt"
        try:
            link.symlink_to(secret)
        except OSError:
            pytest.skip("symlinks are not available")

        assert read_text_bounded(link, 100).text == "outside"
