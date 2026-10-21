"""Tests for Obsidian Vault binding and mtime delta scanning."""

import json
import time
from pathlib import Path

from app.services.wiki.obsidian.binding import scan_vault_mtime_watermark


def test_scan_vault_mtime_watermark(tmp_path: Path):
    vault = tmp_path / "my_vault"
    vault.mkdir()

    file1 = vault / "note1.md"
    file1.write_text("content 1", encoding="utf-8")

    # Past watermark
    t1 = file1.stat().st_mtime
    time.sleep(0.01)

    file2 = vault / "note2.md"
    file2.write_text("content 2", encoding="utf-8")

    canvas_file = vault / "whiteboard.canvas"
    canvas_file.write_text(json.dumps({"nodes": []}), encoding="utf-8")

    res = scan_vault_mtime_watermark(vault, watermark=t1)
    assert res.has_changes is True
    assert "note2.md" in res.modified_files
    assert "whiteboard.canvas" in res.modified_files
    assert "note1.md" not in res.modified_files
