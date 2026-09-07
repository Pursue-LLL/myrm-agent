from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.services.chat.context_bomb_defense_service import (
    ContextBombDefenseService,
    MESSAGE_MAX_CHARS,
)


def test_context_bomb_defense_under_limit(tmp_path: Path) -> None:
    normal_text = "Hello, please review this standard query."
    result = ContextBombDefenseService.process_incoming_content(
        normal_text,
        workspace_root=tmp_path,
        max_chars=MESSAGE_MAX_CHARS,
    )
    assert not result.is_spilled
    assert result.processed_content == normal_text
    assert result.original_char_count == len(normal_text)
    assert result.spillover_path is None


def test_context_bomb_defense_over_limit_spills_file(tmp_path: Path) -> None:
    large_payload = "X" * 20_000
    result = ContextBombDefenseService.process_incoming_content(
        large_payload,
        workspace_root=tmp_path,
        max_chars=1_000,
    )
    assert result.is_spilled
    assert result.original_char_count == 20_000
    assert result.spillover_path is not None
    assert Path(result.spillover_path).exists()
    assert "<file_spillover" in result.processed_content
    assert "read_file" in result.processed_content

    # Check content in spilled file
    saved_text = Path(result.spillover_path).read_text(encoding="utf-8")
    assert saved_text == large_payload


def test_cleanup_transient_spillover_cache(tmp_path: Path) -> None:
    spill_dir = ContextBombDefenseService.get_spillover_dir(tmp_path)
    fresh_file = spill_dir / "spillover_fresh.md"
    fresh_file.write_text("fresh content")

    stale_file = spill_dir / "spillover_stale.md"
    stale_file.write_text("stale content")
    past_time = time.time() - 100_000
    import os
    os.utime(stale_file, (past_time, past_time))

    removed = ContextBombDefenseService.cleanup_transient_spillover_cache(
        workspace_root=tmp_path,
        ttl_seconds=10,
    )
    assert removed == 1
    assert fresh_file.exists()
    assert not stale_file.exists()
