"""The imap-smtp-email skill script lists and saves a message's attachments under the names their senders gave them.

A sender may write a file name as raw UTF-8 in ``Content-Disposition`` or in the ``name`` of ``Content-Type``: the parser
returns a ``Header`` object for such a header and the standard library turns it into replacement characters. Names also
collide, once they are made safe for a file system or when a message carries two files of one name, and a download
must not let one attachment, or a file already in the output directory, replace another.

[INPUT]
- assets/prebuilt_skills/imap-smtp-email/scripts: email_manager.py imported in process
- tests/assets/conftest.py: the script import path
- tests/support/email_skill_inprocess.py: the IMAP double and the in-process ``main``

[OUTPUT]
- Fails when ``read`` or ``download`` loses a file name that is raw UTF-8, RFC 2231 or RFC 2047, when two attachments end
  up in one file, when one replaces a file already in the output directory or is written through a symlink there that
  points nowhere, when a name such as ``../x`` puts a file outside the output directory, when a name of dots only or an
  empty one is saved under any name but ``attachment``, when a name too long for a file system fails the download or leaves a
  copy of it that cannot be numbered, when a write that fails leaves a partial file behind, hides why it failed or does not
  name the files saved before it, when a directory that cannot be written is taken for a name that is taken, when a
  message that repeats one name has no limit on the copies saved, when ``--filename`` misses a name that decodes to it, or
  when a message without attachments is not reported as such

[POS]
In-process test of how ``read`` and ``download`` name attachments, next to ``test_imap_smtp_email_failures.py``, which
covers how they fail.
"""

from __future__ import annotations

import base64
import errno
import json
import os
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

from tests.support.email_skill_inprocess import conn_serving, run_main

_HEAD = (
    "From: eve@example.test\r\nSubject: s\r\nMessage-ID: <1@example.test>\r\nMIME-Version: 1.0\r\n"
    'Content-Type: multipart/mixed; boundary="b"\r\n\r\n--b\r\nContent-Type: text/plain\r\n\r\nhi\r\n'
)


_PDF = "Content-Type: application/pdf"


def _part(content: bytes, *headers: str) -> bytes:
    """One MIME part holding *content*, with *headers* written as raw UTF-8."""
    lines = "".join(f"{line}\r\n" for line in headers)
    return f"--b\r\n{lines}Content-Transfer-Encoding: base64\r\n\r\n".encode() + base64.b64encode(content) + b"\r\n"


def _attachment(name: str | None, content: bytes) -> bytes:
    disposition = "attachment" if name is None else f'attachment; filename="{name}"'
    return _part(content, _PDF, f"Content-Disposition: {disposition}")


def _message(*parts: bytes) -> bytes:
    return _HEAD.encode() + b"".join(parts) + b"--b--\r\n"


def _run(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], raw: bytes, *argv: str
) -> dict[str, object]:
    run_main(email_manager, monkeypatch, conn_serving(raw), *argv)
    answer: dict[str, object] = json.loads(capsys.readouterr().out)
    return answer


def _entries(answer: dict[str, object], key: str) -> list[dict[str, str]]:
    return cast("list[dict[str, str]]", answer[key])


def _saved(directory: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(directory.iterdir())}


class _FullDisk:
    """The file a download creates when the disk is full: it exists, and every write to it fails."""

    def __init__(self, path: Path) -> None:
        self._handle = open(path, "xb")  # noqa: SIM115 -- closed in __exit__

    def __enter__(self) -> _FullDisk:
        return self

    def __exit__(self, *_exc: object) -> None:
        self._handle.close()

    def write(self, _data: bytes) -> int:
        raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))


def _intercept_exclusive_create(monkeypatch: pytest.MonkeyPatch, replacement: Callable[[Path], object]) -> None:
    """Route every ``Path.open(..., "xb")``, which is how the script creates a download, through *replacement*."""
    real_open = Path.open

    def open_(self: Path, mode: str = "r") -> object:
        return replacement(self) if mode == "xb" else real_open(self, mode)

    monkeypatch.setattr(Path, "open", open_)


def _download(
    email_manager: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    raw: bytes,
    directory: Path,
    *extra: str,
) -> dict[str, object]:
    """Run ``download`` of the message *raw* into *directory*; *extra* are further arguments such as ``--filename``."""
    return _run(email_manager, monkeypatch, capsys, raw, "download", "1", *extra, "--output-dir", str(directory))


def _download_fails(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], raw: bytes, directory: Path
) -> str:
    """Download the message *raw* into *directory*, which has to end in the script's JSON error; return its text."""
    with pytest.raises(SystemExit):
        _download(email_manager, monkeypatch, capsys, raw, directory)
    error: str = json.loads(capsys.readouterr().out)["error"]
    return error


# The part headers that give an attachment the name 发票.pdf, in each form a sender may write it.
_NAMED = [
    pytest.param((_PDF, "Content-Disposition: attachment; filename*=UTF-8''%E5%8F%91%E7%A5%A8.pdf"), id="rfc-2231"),
    pytest.param((_PDF, 'Content-Disposition: attachment; filename="=?utf-8?b?5Y+R56Wo?=.pdf"'), id="rfc-2047-with-an-extension"),
    pytest.param((_PDF, 'Content-Disposition: attachment; filename="发票.pdf"'), id="raw-utf-8-disposition"),
    pytest.param((f'{_PDF}; name="发票.pdf"', "Content-Disposition: attachment"), id="raw-utf-8-type-name"),
]


@pytest.mark.parametrize("headers", _NAMED)
def test_read_lists_an_attachment_under_the_name_its_sender_gave_it(
    email_manager: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    headers: tuple[str, ...],
) -> None:
    raw = _message(_part(b"DATA", *headers))

    answer = _run(email_manager, monkeypatch, capsys, raw, "read", "1")

    assert _entries(answer, "attachments") == [{"filename": "发票.pdf", "content_type": "application/pdf"}]


@pytest.mark.parametrize("headers", _NAMED)
def test_download_saves_an_attachment_under_the_name_its_sender_gave_it(
    email_manager: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    headers: tuple[str, ...],
) -> None:
    raw = _message(_part(b"DATA", *headers))

    answer = _download(email_manager, monkeypatch, capsys, raw, tmp_path)

    assert _saved(tmp_path) == {"发票.pdf": b"DATA"}
    assert [(entry["filename"], entry["path"]) for entry in _entries(answer, "files")] == [
        ("发票.pdf", str(tmp_path / "发票.pdf"))
    ]


@pytest.mark.parametrize(
    ("names", "saved"),
    [
        pytest.param(["scan.pdf"] * 3, ["scan.pdf", "scan-1.pdf", "scan-2.pdf"], id="one-name-three-times"),
        pytest.param([None, None], ["attachment", "attachment-1"], id="no-name"),
        pytest.param(["a b.pdf", "a_b.pdf"], ["a_b.pdf", "a_b-1.pdf"], id="names-that-differ-only-in-punctuation"),
        pytest.param(["archive.tar.gz"] * 2, ["archive.tar.gz", "archive.tar-1.gz"], id="two-extensions"),
        pytest.param(["发票.pdf", "合同.pdf"], ["发票.pdf", "合同.pdf"], id="distinct-names-are-left-alone"),
    ],
)
def test_download_gives_every_attachment_a_file_of_its_own(
    email_manager: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    names: list[str | None],
    saved: list[str],
) -> None:
    contents = [f"CONTENT-{number}".encode() for number, _name in enumerate(names)]
    raw = _message(*(_attachment(name, content) for name, content in zip(names, contents, strict=True)))

    answer = _download(email_manager, monkeypatch, capsys, raw, tmp_path)

    assert _saved(tmp_path) == dict(zip(saved, contents, strict=True))
    assert [Path(entry["path"]).name for entry in _entries(answer, "files")] == saved


def test_download_keeps_a_file_that_is_already_in_the_output_directory(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    (tmp_path / "contract.pdf").write_bytes(b"EDITED BY THE USER")

    _download(email_manager, monkeypatch, capsys, _message(_attachment("contract.pdf", b"NEW")), tmp_path)

    assert _saved(tmp_path) == {"contract.pdf": b"EDITED BY THE USER", "contract-1.pdf": b"NEW"}


def test_download_does_not_write_through_a_symlink_that_points_nowhere(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    try:
        (out / "scan.pdf").symlink_to(elsewhere / "target.pdf")
    except (OSError, NotImplementedError):
        pytest.skip("this platform cannot create symlinks")

    answer = _download(email_manager, monkeypatch, capsys, _message(_attachment("scan.pdf", b"NEW")), out)

    assert not (elsewhere / "target.pdf").exists()
    assert (out / "scan-1.pdf").read_bytes() == b"NEW"
    assert [entry["path"] for entry in _entries(answer, "files")] == [str(out / "scan-1.pdf")]


# A file name holds 255 bytes on Linux; 4 of them stay free for the number of a copy, ``-999`` at the most.
@pytest.mark.parametrize(
    ("name", "saved_as"),
    [
        pytest.param("Q3-report_v2.final.pdf", "Q3-report_v2.final.pdf", id="letters-digits-dot-underscore-dash-stay"),
        pytest.param("a:b*c?.pdf", "a_b_c_.pdf", id="characters-a-file-system-reserves-become-underscores"),
        pytest.param("发票 2026.pdf", "发票_2026.pdf", id="a-space-becomes-an-underscore-and-chinese-stays"),
        pytest.param("../evil.pdf", ".._evil.pdf", id="parent-directory"),
        pytest.param("/etc/evil.pdf", "_etc_evil.pdf", id="absolute-path"),
        pytest.param("a/../../b.pdf", "a_.._.._b.pdf", id="climbs-out-from-inside"),
        pytest.param(".", "attachment", id="single-dot"),
        pytest.param("..", "attachment", id="double-dot"),
        pytest.param("...", "attachment", id="three-dots"),
        pytest.param("=?utf-8?b??=", "attachment", id="empty-encoded-word"),
        pytest.param("a" * 251, "a" * 251, id="at-the-limit"),
        pytest.param("a" * 252, "a" * 251, id="one-byte-over"),
        pytest.param("文" * 100 + ".pdf", "文" * 82 + ".pdf", id="chinese-keeps-its-extension-and-whole-characters"),
        pytest.param(f"{'x' * 300}.{'e' * 15}", f"{'x' * 235}.{'e' * 15}", id="a-16-byte-extension-is-kept"),
        pytest.param(f"{'x' * 300}.{'e' * 16}", "x" * 251, id="a-17-byte-tail-is-no-extension-and-is-cut-with-the-name"),
    ],
)
def test_download_saves_each_name_as_one_safe_file_inside_the_output_directory(
    email_manager: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    name: str,
    saved_as: str,
) -> None:
    out = tmp_path / "out"

    _download(email_manager, monkeypatch, capsys, _message(_attachment(name, b"DATA")), out)

    assert [path.name for path in tmp_path.iterdir()] == ["out"]
    assert _saved(out) == {saved_as: b"DATA"}


def test_download_can_number_a_copy_of_a_name_that_fills_the_limit(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    name = "y" * 251 + ".pdf"  # 255 bytes: a number appended to it would exceed the limit
    raw = _message(_attachment(name, b"ONE"), _attachment(name, b"TWO"))

    _download(email_manager, monkeypatch, capsys, raw, tmp_path)

    saved = _saved(tmp_path)
    assert sorted(saved.values()) == [b"ONE", b"TWO"]
    assert all(len(file.encode()) <= 255 for file in saved)


def test_download_leaves_no_partial_file_when_a_write_fails(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _intercept_exclusive_create(monkeypatch, _FullDisk)

    error = _download_fails(email_manager, monkeypatch, capsys, _message(_attachment("big.zip", b"DATA")), tmp_path)

    assert os.strerror(errno.ENOSPC) in error
    assert "already saved" not in error
    assert list(tmp_path.iterdir()) == []


def test_download_names_the_files_it_saved_before_a_write_failed(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def fill_up_at_the_second_file(path: Path) -> object:
        return _FullDisk(path) if path.name == "two.pdf" else open(path, "xb")  # noqa: SIM115 -- closed by the script

    _intercept_exclusive_create(monkeypatch, fill_up_at_the_second_file)
    raw = _message(_attachment("one.pdf", b"ONE"), _attachment("two.pdf", b"TWO"))

    error = _download_fails(email_manager, monkeypatch, capsys, raw, tmp_path)

    assert os.strerror(errno.ENOSPC) in error
    assert error.endswith(f"already saved: {tmp_path / 'one.pdf'}")
    assert _saved(tmp_path) == {"one.pdf": b"ONE"}


def test_download_reports_why_a_write_failed_even_when_the_partial_file_cannot_be_removed(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _intercept_exclusive_create(monkeypatch, _FullDisk)

    def refuse_to_unlink(_path: Path, *_args: object, **_kwargs: object) -> None:
        raise PermissionError(errno.EACCES, os.strerror(errno.EACCES))

    monkeypatch.setattr(Path, "unlink", refuse_to_unlink)

    error = _download_fails(email_manager, monkeypatch, capsys, _message(_attachment("big.zip", b"DATA")), tmp_path)

    assert os.strerror(errno.ENOSPC) in error


def test_download_does_not_take_an_unwritable_directory_for_a_name_that_is_taken(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    attempts: list[Path] = []

    def refuse(path: Path) -> object:
        attempts.append(path)
        raise PermissionError(errno.EACCES, os.strerror(errno.EACCES))

    _intercept_exclusive_create(monkeypatch, refuse)

    error = _download_fails(email_manager, monkeypatch, capsys, _message(_attachment("scan.pdf", b"DATA")), tmp_path)

    assert os.strerror(errno.EACCES) in error
    assert attempts == [tmp_path / "scan.pdf"]


def test_download_stops_when_one_name_has_been_saved_as_often_as_allowed(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setattr("mail_client.attachments.MAX_SAME_NAME", 3)
    raw = _message(*(_attachment("scan.pdf", b"DATA") for _ in range(4)))

    error = _download_fails(email_manager, monkeypatch, capsys, raw, tmp_path)

    saved = ", ".join(str(tmp_path / name) for name in ("scan.pdf", "scan-1.pdf", "scan-2.pdf"))
    assert error == (
        f"Email command 'download' failed: Too many files named scan.pdf in {tmp_path}; "
        f"remove some of them or pass a different --output-dir; already saved: {saved}"
    )
    assert sorted(_saved(tmp_path)) == ["scan-1.pdf", "scan-2.pdf", "scan.pdf"]


def test_the_filename_filter_matches_the_decoded_name(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    raw = _message(_attachment("发票.pdf", b"INVOICE"), _attachment("合同.pdf", b"CONTRACT"))

    _download(email_manager, monkeypatch, capsys, raw, tmp_path, "--filename", "发票")

    assert _saved(tmp_path) == {"发票.pdf": b"INVOICE"}


def test_a_message_without_attachments_is_reported_as_such(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    answer = _download(email_manager, monkeypatch, capsys, _message(), tmp_path)

    assert answer["status"] == "no_attachments"
    assert _saved(tmp_path) == {}
