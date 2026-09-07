from __future__ import annotations

import hashlib
import time
from pathlib import Path

from app.services.chat.context_bomb_defense_service import ContextBombDefenseService


def test_process_incoming_content_under_threshold(tmp_path: Path) -> None:
    text = "Short user prompt."
    res = ContextBombDefenseService.process_incoming_content(
        text,
        workspace_root=tmp_path,
        max_chars=100,
    )
    assert not res.is_spilled
    assert res.processed_content == text
    assert res.original_char_count == len(text)
    assert res.spillover_path is None


def test_process_incoming_content_over_threshold(tmp_path: Path) -> None:
    raw_content = "X" * 300 + "\nDetailed instructions follow here..."
    res = ContextBombDefenseService.process_incoming_content(
        raw_content,
        chat_id="chat-123",
        workspace_root=tmp_path,
        max_chars=100,
    )

    assert res.is_spilled
    assert res.original_char_count == len(raw_content)
    assert res.spillover_path is not None
    assert res.content_sha256 == hashlib.sha256(raw_content.encode("utf-8")).hexdigest()

    saved_file = Path(res.spillover_path)
    assert saved_file.exists()
    assert saved_file.read_text(encoding="utf-8") == raw_content

    # Check structural prompt injection
    assert "<file_spillover path=" in res.processed_content
    assert res.content_sha256 in res.processed_content
    assert "read_file" in res.processed_content


def test_cleanup_transient_spillover_cache(tmp_path: Path) -> None:
    spill_dir = ContextBombDefenseService.get_spillover_dir(tmp_path)
    old_file = spill_dir / "spillover_old.md"
    fresh_file = spill_dir / "spillover_fresh.md"

    old_file.write_text("old text", encoding="utf-8")
    fresh_file.write_text("fresh text", encoding="utf-8")

    import os
    past = time.time() - 1000
    os.utime(old_file, (past, past))

    purged = ContextBombDefenseService.cleanup_transient_spillover_cache(
        workspace_root=tmp_path,
        ttl_seconds=100,
    )
    assert purged == 1
    assert not old_file.exists()
    assert fresh_file.exists()
