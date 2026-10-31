"""Tests for layout QA observer.

The conversion runs against a stand-in ``soffice`` shell script, so what is pinned is how the observer judges the
process (exit code, output, deadline, cancel), not LibreOffice itself.
"""

from __future__ import annotations

import asyncio
import sys
import time
import zipfile
from pathlib import Path

import psutil
import pytest

from myrm_agent_harness.agent.meta_tools.file_ops.observers.layout_qa_observer import (
    run_layout_qa_check,
)

_MODULE = "myrm_agent_harness.agent.meta_tools.file_ops.observers.layout_qa_observer"
_posix_only = pytest.mark.skipif(sys.platform == "win32", reason="the stand-in soffice is a POSIX shell script")
# What a test that fails because a conversion never ends may wait before it reports so.
_GUARD_SECONDS = 15
# Arguments are `--headless --convert-to pdf --outdir <dir> <document>`: $5 is the output directory, $6 the document.
_CONVERTS = 'head -c 256 /dev/zero > "$5/$(basename "$6" .docx).pdf"'
# A background child that holds the conversion's pipes, as `soffice.bin` does behind the `soffice` launcher.
_NEVER_ENDS = {
    "hangs": "sleep 600 &\necho $! > {pid_file}\nwait",
    "exits-first": "sleep 600 &\necho $! > {pid_file}\nexit 0",
}


def _install_soffice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> Path:
    """Make `soffice` a shell script that runs *body*; returns the document to check."""
    script = tmp_path / "soffice"
    script.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setattr(f"{_MODULE}.shutil.which", lambda _name: str(script))
    docx_path = tmp_path / "report.docx"
    _write_minimal_docx(docx_path)
    return docx_path


async def _stops_running(pid: int, within: float = 2.0) -> bool:
    """Whether the process stops running within *within* seconds: SIGKILL is delivered asynchronously, so a process
    that was just killed can still be listed for a few milliseconds."""
    deadline = time.monotonic() + within
    while True:
        try:
            if psutil.Process(pid).status() == psutil.STATUS_ZOMBIE:
                return True
        except psutil.NoSuchProcess:
            return True
        if time.monotonic() >= deadline:
            return False
        await asyncio.sleep(0.01)


def _write_minimal_docx(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", b"<Types/>")
        archive.writestr(
            "word/document.xml",
            b"""<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body/></w:document>""",
        )


@pytest.mark.asyncio
async def test_layout_qa_skips_silently_without_soffice(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docx_path = tmp_path / "report.docx"
    _write_minimal_docx(docx_path)
    monkeypatch.setattr(
        "myrm_agent_harness.agent.meta_tools.file_ops.observers.layout_qa_observer.shutil.which",
        lambda _name: None,
    )

    warnings = await run_layout_qa_check(docx_path)

    assert warnings == []


@_posix_only
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (_CONVERTS, []),
        (
            "echo 'no display' >&2; exit 3",
            ["Layout QA failed: soffice could not convert report.docx (exit 3). no display"],
        ),
        ("exit 0", ["Layout QA failed: converted PDF for report.docx is missing or empty."]),
    ],
    ids=["converted", "exit-code", "no-pdf"],
)
async def test_a_conversion_that_ends_is_judged_by_its_exit_code_and_output(
    body: str, expected: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docx_path = _install_soffice(tmp_path, monkeypatch, body)

    assert await run_layout_qa_check(docx_path) == expected


@_posix_only
@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", list(_NEVER_ENDS))
async def test_a_conversion_that_does_not_finish_is_stopped_with_everything_it_started(
    scenario: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid_file = tmp_path / "child.pid"
    docx_path = _install_soffice(tmp_path, monkeypatch, _NEVER_ENDS[scenario].format(pid_file=pid_file))
    monkeypatch.setattr(f"{_MODULE}._CONVERT_TIMEOUT_SECONDS", 1.0)

    async with asyncio.timeout(_GUARD_SECONDS):
        warnings = await run_layout_qa_check(docx_path)

    assert warnings == ["Layout QA failed: soffice did not finish converting report.docx within 1s."]
    assert await _stops_running(int(pid_file.read_text()))


@_posix_only
@pytest.mark.asyncio
async def test_a_cancelled_check_stops_what_it_started(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pid_file = tmp_path / "child.pid"
    docx_path = _install_soffice(tmp_path, monkeypatch, _NEVER_ENDS["hangs"].format(pid_file=pid_file))

    task = asyncio.create_task(run_layout_qa_check(docx_path))
    async with asyncio.timeout(_GUARD_SECONDS):
        while not (pid_file.exists() and pid_file.read_text().strip()):
            await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert await _stops_running(int(pid_file.read_text()))
