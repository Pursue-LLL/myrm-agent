"""Writing side of the workspace text editor I/O.

Compare-and-swap saves that leave everything untouched byte-identical, the Windows retry policy, and exclusive
create for copies.
"""

from __future__ import annotations

import errno
import hashlib
import os
import stat
import threading
from pathlib import Path

import pytest

from app.services.files import text_edit_io
from app.services.files.text_edit_io import (
    EDITABLE_MAX_BYTES,
    InvalidContent,
    NotEditable,
    TextStyle,
    VersionConflict,
    WriteBlocked,
    create_text_file_exclusive,
    write_text_if_version,
)

BOM = b"\xef\xbb\xbf"


def _file(tmp_path: Path, data: bytes, name: str = "note.txt") -> str:
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------------------
# Saving: compare-and-swap, byte-exact restore
# --------------------------------------------------------------------------------------


def test_save_replaces_content_and_returns_the_new_version(tmp_path: Path) -> None:
    raw = b"one\ntwo\n"
    path = _file(tmp_path, raw)

    outcome = write_text_if_version(path, "one\nTWO\n", _sha(raw))

    assert Path(path).read_bytes() == b"one\nTWO\n"
    assert outcome.changed
    assert outcome.version == _sha(b"one\nTWO\n")
    assert outcome.size == 8


@pytest.mark.parametrize(
    ("original", "edited", "expected"),
    [
        (b"a\r\nb\r\n", "a\nB\n", b"a\r\nB\r\n"),
        (BOM + b"a\nb\n", "a\nB\n", BOM + b"a\nB\n"),
        (BOM + b"a\r\nb\r\n", "a\r\nB\n", BOM + b"a\r\nB\r\n"),
        (b"a\nb", "a\nb\nc", b"a\nb\nc"),
    ],
)
def test_save_restores_the_files_own_line_endings_and_bom(tmp_path: Path, original: bytes, edited: str, expected: bytes) -> None:
    path = _file(tmp_path, original)
    write_text_if_version(path, edited, _sha(original))
    assert Path(path).read_bytes() == expected


def test_unchanged_text_is_not_written(tmp_path: Path) -> None:
    raw = b"keep\r\nme\r\n"
    path = _file(tmp_path, raw)
    os.utime(path, ns=(1_000_000_000, 1_000_000_000))

    outcome = write_text_if_version(path, "keep\nme\n", _sha(raw))

    assert not outcome.changed
    assert outcome.version == _sha(raw)
    assert os.stat(path).st_mtime_ns == 1_000_000_000


def test_stale_version_is_refused_and_the_file_is_left_alone(tmp_path: Path) -> None:
    path = _file(tmp_path, b"agent wrote this\n")

    with pytest.raises(VersionConflict) as conflict:
        write_text_if_version(path, "user edit\n", _sha(b"what the user opened\n"))

    assert conflict.value.current_version == _sha(b"agent wrote this\n")
    assert Path(path).read_bytes() == b"agent wrote this\n"


def test_touching_a_file_without_changing_bytes_is_not_a_conflict(tmp_path: Path) -> None:
    raw = b"same bytes\n"
    path = _file(tmp_path, raw)
    os.utime(path, ns=(5_000_000_000, 5_000_000_000))

    write_text_if_version(path, "edited\n", _sha(raw))

    assert Path(path).read_bytes() == b"edited\n"


def test_overwrite_after_conflict_means_saving_against_the_current_version(tmp_path: Path) -> None:
    path = _file(tmp_path, b"v1\n")
    with pytest.raises(VersionConflict) as conflict:
        write_text_if_version(path, "mine\n", _sha(b"v0\n"))

    write_text_if_version(path, "mine\n", conflict.value.current_version)

    assert Path(path).read_bytes() == b"mine\n"


@pytest.mark.parametrize(
    ("raw", "reason"),
    [(b"a\x00b", "binary"), (b"\xff\xfe\xfa", "not_utf8"), (b"a\r\nb\n", "mixed_line_endings")],
)
def test_a_file_that_cannot_round_trip_is_never_written(tmp_path: Path, raw: bytes, reason: str) -> None:
    path = _file(tmp_path, raw)
    with pytest.raises(NotEditable) as refused:
        write_text_if_version(path, "x", _sha(raw))
    assert refused.value.reason == reason
    assert Path(path).read_bytes() == raw


def test_a_file_that_grew_past_the_limit_is_refused_without_hashing(tmp_path: Path) -> None:
    path = _file(tmp_path, b"x" * (EDITABLE_MAX_BYTES + 1))
    with pytest.raises(NotEditable) as refused:
        write_text_if_version(path, "x", "0" * 64)
    assert refused.value.reason == "too_large"


@pytest.mark.parametrize(
    ("text", "issue"),
    [("a\x00b", "contains_nul"), ("lone \ud800 surrogate", "not_utf8"), ("x" * (EDITABLE_MAX_BYTES + 1), "too_large")],
)
def test_text_that_would_make_the_file_uneditable_is_refused(tmp_path: Path, text: str, issue: str) -> None:
    raw = b"ok\n"
    path = _file(tmp_path, raw)
    with pytest.raises(InvalidContent) as refused:
        write_text_if_version(path, text, _sha(raw))
    assert refused.value.issue == issue
    assert Path(path).read_bytes() == raw


def test_crlf_growth_past_the_limit_is_refused(tmp_path: Path) -> None:
    lines = (EDITABLE_MAX_BYTES // 2) + 10
    raw = b"x\r\n"
    path = _file(tmp_path, raw)
    with pytest.raises(InvalidContent) as refused:
        write_text_if_version(path, "x\n" * lines, _sha(raw))
    assert refused.value.issue == "too_large"


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_permission_bits_survive_a_save(tmp_path: Path) -> None:
    raw = b"#!/bin/sh\necho hi\n"
    path = _file(tmp_path, raw, "run.sh")
    os.chmod(path, 0o640)

    write_text_if_version(path, "#!/bin/sh\necho bye\n", _sha(raw))

    assert stat.S_IMODE(os.stat(path).st_mode) == 0o640


@pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0), reason="needs a non-root POSIX user")
def test_a_read_only_file_is_not_replaced_by_rename(tmp_path: Path) -> None:
    raw = b"locked\n"
    path = _file(tmp_path, raw)
    os.chmod(path, 0o444)

    with pytest.raises(WriteBlocked):
        write_text_if_version(path, "edited\n", _sha(raw))

    assert Path(path).read_bytes() == raw


def test_a_failed_write_keeps_the_original_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = b"precious\n"
    path = _file(tmp_path, raw)

    def disk_full(*_args: object, **_kwargs: object) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(text_edit_io, "atomic_write", disk_full)
    with pytest.raises(OSError, match="No space"):
        write_text_if_version(path, "replacement\n", _sha(raw))

    assert Path(path).read_bytes() == raw


def test_concurrent_saves_from_one_version_have_exactly_one_winner(tmp_path: Path) -> None:
    raw = b"start\n"
    path = _file(tmp_path, raw)
    base = _sha(raw)
    barrier = threading.Barrier(8)
    results: list[object] = []

    def save(index: int) -> None:
        barrier.wait()
        try:
            results.append(write_text_if_version(path, f"writer {index}\n", base))
        except VersionConflict as conflict:
            results.append(conflict)

    threads = [threading.Thread(target=save, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    winners = [r for r in results if not isinstance(r, VersionConflict)]
    assert len(winners) == 1 and len(results) == 8
    assert Path(path).read_bytes().startswith(b"writer ")


# --------------------------------------------------------------------------------------
# Windows: a file held open for a moment is retried, then reported
# --------------------------------------------------------------------------------------


def _flaky_atomic_write(failures: int, calls: list[int]):
    def flaky(path: str, data: bytes, *, mode: int | None = None) -> None:
        calls.append(1)
        if len(calls) <= failures:
            raise PermissionError(13, "The process cannot access the file")
        Path(path).write_bytes(data)

    return flaky


def test_a_briefly_locked_file_is_retried_where_the_platform_needs_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = b"locked briefly\n"
    path = _file(tmp_path, raw)
    calls: list[int] = []
    monkeypatch.setattr(text_edit_io, "_RETRY_ON_PERMISSION_ERROR", True)
    monkeypatch.setattr(text_edit_io, "_REPLACE_RETRY_DELAY_S", 0)
    monkeypatch.setattr(text_edit_io, "atomic_write", _flaky_atomic_write(2, calls))

    write_text_if_version(path, "saved\n", _sha(raw))

    assert len(calls) == 3
    assert Path(path).read_bytes() == b"saved\n"


def test_a_file_that_stays_locked_is_reported_after_bounded_retries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = b"locked\n"
    path = _file(tmp_path, raw)
    calls: list[int] = []
    monkeypatch.setattr(text_edit_io, "_RETRY_ON_PERMISSION_ERROR", True)
    monkeypatch.setattr(text_edit_io, "_REPLACE_RETRY_DELAY_S", 0)
    monkeypatch.setattr(text_edit_io, "atomic_write", _flaky_atomic_write(99, calls))

    with pytest.raises(WriteBlocked):
        write_text_if_version(path, "saved\n", _sha(raw))

    assert len(calls) == text_edit_io._REPLACE_ATTEMPTS
    assert Path(path).read_bytes() == raw


def test_where_retry_is_not_needed_a_refusal_is_reported_at_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    raw = b"nope\n"
    path = _file(tmp_path, raw)
    calls: list[int] = []
    monkeypatch.setattr(text_edit_io, "_RETRY_ON_PERMISSION_ERROR", False)
    monkeypatch.setattr(text_edit_io, "atomic_write", _flaky_atomic_write(99, calls))

    with pytest.raises(WriteBlocked):
        write_text_if_version(path, "saved\n", _sha(raw))

    assert len(calls) == 1


# --------------------------------------------------------------------------------------
# Exclusive create (save as copy)
# --------------------------------------------------------------------------------------


def test_exclusive_create_writes_in_the_given_style(tmp_path: Path) -> None:
    target = tmp_path / "copy.txt"

    outcome = create_text_file_exclusive(str(target), "a\nb\n", TextStyle("crlf", True))

    assert target.read_bytes() == BOM + b"a\r\nb\r\n"
    assert outcome.version == _sha(target.read_bytes())


def test_exclusive_create_never_overwrites(tmp_path: Path) -> None:
    target = tmp_path / "taken.txt"
    target.write_bytes(b"mine\n")

    with pytest.raises(FileExistsError):
        create_text_file_exclusive(str(target), "other\n", TextStyle())

    assert target.read_bytes() == b"mine\n"


def test_exclusive_create_refuses_text_that_would_be_uneditable_and_leaves_nothing_behind(tmp_path: Path) -> None:
    target = tmp_path / "bad.txt"
    with pytest.raises(InvalidContent):
        create_text_file_exclusive(str(target), "a\x00b", TextStyle())
    assert not target.exists()
