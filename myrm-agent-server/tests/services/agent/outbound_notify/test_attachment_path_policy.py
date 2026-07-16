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


def test_rejects_blank_path() -> None:
    assert is_local_attachment_path_allowed("   ", ("/tmp",)) is False


def test_skips_blank_root_entry(tmp_path: Path) -> None:
    file_path = tmp_path / "report.pdf"
    file_path.write_bytes(b"data")
    assert is_local_attachment_path_allowed(str(file_path), ("", str(tmp_path))) is True


def test_rejects_when_no_root_matches(tmp_path: Path) -> None:
    other_root = tmp_path / "allowed"
    other_root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"x")
    assert is_local_attachment_path_allowed(str(outside), (str(other_root / "nested-only"),)) is False


def test_rejects_path_traversal_escape(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    traversal = str(nested / ".." / ".." / "etc" / "passwd")
    assert is_local_attachment_path_allowed(traversal, (str(nested),)) is False


def test_returns_false_when_path_resolve_raises(monkeypatch) -> None:
    from unittest.mock import patch

    with patch.object(Path, "resolve", side_effect=OSError("resolve failed")):
        assert is_local_attachment_path_allowed("/any/path", ("/tmp",)) is False


def test_returns_false_when_root_resolve_raises(tmp_path: Path) -> None:
    from unittest.mock import patch

    file_path = tmp_path / "file.txt"
    file_path.write_bytes(b"x")
    original_resolve = Path.resolve
    call_count = {"n": 0}

    def _resolve(self: Path, *, strict: bool = False) -> Path:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return original_resolve(self, strict=strict)
        raise OSError("root resolve failed")

    with patch.object(Path, "resolve", _resolve):
        assert is_local_attachment_path_allowed(str(file_path), (str(tmp_path),)) is False
