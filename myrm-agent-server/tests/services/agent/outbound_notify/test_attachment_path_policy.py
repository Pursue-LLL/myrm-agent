"""Unit tests for attachment_path_policy."""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.services.agent.outbound_notify.attachment_path_policy import is_local_attachment_path_allowed


def test_rejects_empty_allowed_roots() -> None:
    assert is_local_attachment_path_allowed("/tmp/file.txt", ()) is False


def test_allows_path_under_allowed_root(tmp_path: Path) -> None:
    file_path = tmp_path / "report.pdf"
    file_path.write_bytes(b"data")
    assert is_local_attachment_path_allowed(str(file_path), (str(tmp_path),)) is True


def test_rejects_path_outside_allowed_root(tmp_path: Path) -> None:
    with tempfile.NamedTemporaryFile(delete=False) as outside:
        outside_path = outside.name
    try:
        assert is_local_attachment_path_allowed(outside_path, (str(tmp_path),)) is False
    finally:
        Path(outside_path).unlink(missing_ok=True)


def test_rejects_path_traversal_escape(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    traversal = str(nested / ".." / ".." / "etc" / "passwd")
    assert is_local_attachment_path_allowed(traversal, (str(nested),)) is False
