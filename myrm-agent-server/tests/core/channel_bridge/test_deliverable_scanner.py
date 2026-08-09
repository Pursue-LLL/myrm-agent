"""Unit tests for channel deliverable path scanner."""

from __future__ import annotations

from pathlib import Path

from app.core.channel_bridge.agent_executor.deliverable_path_scanner import (
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
    stripped, attachments = collect_deliverable_paths_from_text(
        text,
        workspace_root=str(tmp_path),
    )
    assert len(attachments) == 1
    assert attachments[0].filename == "output.csv"
    assert "workspace/output.csv" not in stripped


def test_attachment_only_reply_strips_path_only_content(tmp_path: Path) -> None:
    report = tmp_path / "only.pdf"
    report.write_bytes(b"%PDF")
    stripped, attachments = collect_deliverable_paths_from_text(
        "workspace/only.pdf",
        workspace_root=str(tmp_path),
    )
    assert len(attachments) == 1
    assert stripped == ""


def test_skips_missing_files(tmp_path: Path) -> None:
    _, attachments = collect_deliverable_paths_from_text(
        "See workspace/missing.pdf",
        workspace_root=str(tmp_path),
    )
    assert attachments == []
