"""Unit tests for channel deliverable path scanner."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.channel_bridge.agent_executor.deliverable.scanner import (
    collect_deliverable_paths_from_text,
    extract_deliverable_path_tokens,
    resolve_deliverable_path,
)


def test_extract_ignores_inline_code(tmp_path: Path) -> None:
    text = "Saved to `workspace/secret.py` but see workspace/report.pdf"
    tokens = extract_deliverable_path_tokens(text)
    assert tokens == ["workspace/report.pdf"]


def test_resolve_workspace_relative(tmp_path: Path) -> None:
    report = tmp_path / "reports" / "brief.pdf"
    report.parent.mkdir(parents=True)
    report.write_bytes(b"%PDF-1.4")
    resolved = resolve_deliverable_path("workspace/reports/brief.pdf", str(tmp_path))
    assert resolved == report.resolve()


def test_collect_attachments_and_strip_text(tmp_path: Path) -> None:
    report = tmp_path / "output.csv"
    report.write_text("a,b\n1,2")
    text = "Done. Delivered workspace/output.csv for review."
    stripped, attachments, oversized, compressed, tmp_paths = (
        collect_deliverable_paths_from_text(
            text,
            workspace_root=str(tmp_path),
        )
    )
    assert len(attachments) == 1
    assert attachments[0].filename == "output.csv"
    assert "workspace/output.csv" not in stripped
    assert oversized == []
    assert compressed == []
    assert tmp_paths == []


def test_attachment_only_reply_strips_path_only_content(tmp_path: Path) -> None:
    report = tmp_path / "only.pdf"
    report.write_bytes(b"%PDF")
    stripped, attachments, _, _, _ = collect_deliverable_paths_from_text(
        "workspace/only.pdf",
        workspace_root=str(tmp_path),
    )
    assert len(attachments) == 1
    assert stripped == ""


def test_skips_missing_files(tmp_path: Path) -> None:
    _, attachments, _, _, _ = collect_deliverable_paths_from_text(
        "See workspace/missing.pdf",
        workspace_root=str(tmp_path),
    )
    assert attachments == []


def test_oversized_image_compressed_into_attachment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PIL import Image

    from app.core.channel_bridge.agent_executor.deliverable import scanner

    monkeypatch.setattr(
        scanner, "MAX_CHANNEL_ATTACHMENT_BYTES", 50_000
    )
    img = tmp_path / "big_chart.png"
    Image.effect_noise((400, 400), 90).convert("RGB").save(img, format="PNG")

    stripped, attachments, oversized, compressed, tmp_paths = (
        collect_deliverable_paths_from_text(
            "Chart: workspace/big_chart.png",
            workspace_root=str(tmp_path),
        )
    )
    assert oversized == []
    assert len(compressed) == 1
    assert compressed[0][0] == "big_chart.png"
    assert len(attachments) == 1
    assert attachments[0].filename == "big_chart.png"
    assert attachments[0].path is not None
    assert attachments[0].path != str(img.resolve())
    assert attachments[0].mime_type == "image/png"
    assert len(tmp_paths) == 1
    assert tmp_paths[0] == attachments[0].path
    assert "workspace/big_chart.png" not in stripped
    for p in tmp_paths:
        Path(p).unlink(missing_ok=True)


def test_oversized_webp_compressed_filename_aligned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WEBP sources re-encode as JPEG; the attachment filename and mime must follow."""
    from PIL import Image

    from app.core.channel_bridge.agent_executor.deliverable import scanner

    monkeypatch.setattr(
        scanner, "MAX_CHANNEL_ATTACHMENT_BYTES", 50_000
    )
    img = tmp_path / "hero.webp"
    Image.effect_noise((400, 400), 90).convert("RGB").save(img, format="WEBP")

    _, attachments, _, _, tmp_paths = collect_deliverable_paths_from_text(
        "Poster: workspace/hero.webp",
        workspace_root=str(tmp_path),
    )
    assert len(attachments) == 1
    assert attachments[0].filename == "hero.jpg"
    assert attachments[0].mime_type == "image/jpeg"
    assert attachments[0].path is not None
    assert attachments[0].path.endswith(".jpg")
    for p in tmp_paths:
        Path(p).unlink(missing_ok=True)


def test_oversized_non_image_reported_as_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.channel_bridge.agent_executor.deliverable import scanner

    monkeypatch.setattr(scanner, "MAX_CHANNEL_ATTACHMENT_BYTES", 100)
    doc = tmp_path / "report.pdf"
    doc.write_bytes(b"%PDF-1.4" + b"x" * 500)

    stripped, attachments, oversized, compressed, tmp_paths = (
        collect_deliverable_paths_from_text(
            "See workspace/report.pdf",
            workspace_root=str(tmp_path),
        )
    )
    assert attachments == []
    assert compressed == []
    assert tmp_paths == []
    assert oversized == [("report.pdf", "508 B")]
    assert "workspace/report.pdf" not in stripped


def test_oversized_uncompressible_image_reported_as_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.channel_bridge.agent_executor.deliverable import scanner

    monkeypatch.setattr(scanner, "MAX_CHANNEL_ATTACHMENT_BYTES", 100)
    img = tmp_path / "photo.gif"
    img.write_bytes(b"GIF89a" + b"x" * 500)

    _, attachments, oversized, compressed, tmp_paths = (
        collect_deliverable_paths_from_text(
            "Photo: workspace/photo.gif",
            workspace_root=str(tmp_path),
        )
    )
    assert attachments == []
    assert compressed == []
    assert tmp_paths == []
    assert oversized[0][0] == "photo.gif"


def test_resolve_rejects_path_traversal(tmp_path: Path) -> None:
    """Tokens escaping the workspace root must never resolve to a file."""
    secret = tmp_path.parent / "secret.pdf"
    secret.write_bytes(b"%PDF-1.4")
    resolved = resolve_deliverable_path("../secret.pdf", str(tmp_path))
    assert resolved is None


def test_resolve_rejects_missing_extension(tmp_path: Path) -> None:
    f = tmp_path / "notes.txt"
    f.write_text("hello")
    assert resolve_deliverable_path("workspace/notes", str(tmp_path)) is None
    assert resolve_deliverable_path("", str(tmp_path)) is None
    assert resolve_deliverable_path("workspace/notes.txt", None) is None


def test_resolve_plain_relative_path(tmp_path: Path) -> None:
    """A bare relative path (no workspace/ prefix) resolves inside root."""
    report = tmp_path / "out.md"
    report.write_text("# done")
    assert resolve_deliverable_path("out.md", str(tmp_path)) == report.resolve()


def test_collect_skips_empty_file(tmp_path: Path) -> None:
    empty = tmp_path / "empty.csv"
    empty.write_bytes(b"")
    text, attachments, oversized, compressed, tmp_paths = (
        collect_deliverable_paths_from_text(
            "Here: workspace/empty.csv",
            workspace_root=str(tmp_path),
        )
    )
    assert attachments == []
    assert oversized == []
    assert compressed == []
    assert tmp_paths == []
    assert "workspace/empty.csv" in text


def test_collect_deduplicates_against_existing_filenames(tmp_path: Path) -> None:
    """A filename already attached by another source is dropped (token removed)."""
    dup = tmp_path / "report.pdf"
    dup.write_bytes(b"%PDF-1.4")
    text, attachments, _oversized, _compressed, _tmp = (
        collect_deliverable_paths_from_text(
            "See workspace/report.pdf",
            workspace_root=str(tmp_path),
            existing_filenames={"report.pdf"},
        )
    )
    assert attachments == []
    assert "workspace/report.pdf" not in text


def test_collect_returns_input_when_no_tokens(tmp_path: Path) -> None:
    text, attachments, oversized, compressed, tmp_paths = (
        collect_deliverable_paths_from_text(
            "No files here.",
            workspace_root=str(tmp_path),
        )
    )
    assert text == "No files here."
    assert attachments == []
    assert oversized == []
    assert compressed == []
    assert tmp_paths == []


def test_extract_deduplicates_and_normalizes_tokens(tmp_path: Path) -> None:
    """Duplicate tokens collapse; trailing punctuation is stripped."""
    tokens = extract_deliverable_path_tokens(
        "See workspace/a.md and workspace/a.md and workspace/b.pdf."
    )
    assert tokens == ["workspace/a.md", "workspace/b.pdf"]


@pytest.mark.asyncio
async def test_resolve_chat_workspace_root_db_hit() -> None:
    """Returns a non-empty workspace_dir from the Chat row."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    from app.core.channel_bridge.agent_executor.deliverable.scanner import (
        resolve_chat_workspace_root,
    )

    mock_db = AsyncMock()
    mock_db.execute.return_value = SimpleNamespace(
        scalar_one_or_none=lambda: " /tmp/ws "
    )
    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__.return_value = mock_db

    with patch(
        "app.database.connection.get_session",
    ) as get_session:
        get_session.return_value = mock_session_cm
        result = await resolve_chat_workspace_root("chat-1")

    assert result == "/tmp/ws"
    mock_db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_chat_workspace_root_empty_or_error() -> None:
    """Empty/None workspace_dir or a DB exception both yield None."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    from app.core.channel_bridge.agent_executor.deliverable.scanner import (
        resolve_chat_workspace_root,
    )

    for value in (None, "   "):
        mock_db = AsyncMock()
        mock_db.execute.return_value = SimpleNamespace(
            scalar_one_or_none=lambda v=value: v
        )
        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__.return_value = mock_db
        with patch(
            "app.database.connection.get_session",
        ) as get_session:
            get_session.return_value = mock_session_cm
            assert await resolve_chat_workspace_root("chat-1") is None

    mock_db = AsyncMock()
    mock_db.execute.side_effect = RuntimeError("db down")
    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__.return_value = mock_db
    with patch(
        "app.database.connection.get_session",
    ) as get_session:
        get_session.return_value = mock_session_cm
        assert await resolve_chat_workspace_root("chat-1") is None
