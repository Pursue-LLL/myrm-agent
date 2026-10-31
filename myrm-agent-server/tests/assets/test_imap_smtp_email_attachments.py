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
  up in one file or one replaces a file already in the output directory, when ``--filename`` misses a name that decodes
  to it, or when a message without attachments is not reported as such

[POS]
In-process test of how ``read`` and ``download`` name attachments, next to ``test_imap_smtp_email_failures.py``, which
covers how they fail.
"""

from __future__ import annotations

import base64
import json
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

    answer = _run(email_manager, monkeypatch, capsys, raw, "download", "1", "--output-dir", str(tmp_path))

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

    answer = _run(email_manager, monkeypatch, capsys, raw, "download", "1", "--output-dir", str(tmp_path))

    assert _saved(tmp_path) == dict(zip(saved, contents, strict=True))
    assert [Path(entry["path"]).name for entry in _entries(answer, "files")] == saved


def test_download_keeps_a_file_that_is_already_in_the_output_directory(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    (tmp_path / "contract.pdf").write_bytes(b"EDITED BY THE USER")

    _run(
        email_manager,
        monkeypatch,
        capsys,
        _message(_attachment("contract.pdf", b"NEW")),
        "download",
        "1",
        "--output-dir",
        str(tmp_path),
    )

    assert _saved(tmp_path) == {"contract.pdf": b"EDITED BY THE USER", "contract-1.pdf": b"NEW"}


def test_the_filename_filter_matches_the_decoded_name(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    raw = _message(_attachment("发票.pdf", b"INVOICE"), _attachment("合同.pdf", b"CONTRACT"))

    _run(email_manager, monkeypatch, capsys, raw, "download", "1", "--filename", "发票", "--output-dir", str(tmp_path))

    assert _saved(tmp_path) == {"发票.pdf": b"INVOICE"}


def test_a_message_without_attachments_is_reported_as_such(
    email_manager: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    answer = _run(email_manager, monkeypatch, capsys, _message(), "download", "1", "--output-dir", str(tmp_path))

    assert answer["status"] == "no_attachments"
    assert _saved(tmp_path) == {}
