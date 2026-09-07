from __future__ import annotations

import os
import time
from pathlib import Path

from app.services.chat.context_bomb_guard import (
    ContextBombDefenseService,
    extract_text_from_query,
)


def test_extract_text_from_query() -> None:
    assert extract_text_from_query("simple string") == "simple string"
    assert extract_text_from_query([{"type": "text", "text": "hello"}, {"type": "text", "text": "world"}]) == "hello\nworld"
    assert extract_text_from_query([{"content": "direct content"}]) == "direct content"
    assert extract_text_from_query(12345) == ""


def test_guard_and_spill_query_under_limit(tmp_path: Path) -> None:
    service = ContextBombDefenseService(max_chars=100)
    query = "Short user prompt"
    transformed, is_spilled, meta = service.guard_and_spill_query(query, workspace_dir=tmp_path)

    assert is_spilled is False
    assert transformed == query
    assert meta is None


def test_guard_and_spill_query_over_limit_spills(tmp_path: Path) -> None:
    service = ContextBombDefenseService(max_chars=50, preview_chars=15)
    query = "X" * 120
    transformed, is_spilled, meta = service.guard_and_spill_query(
        query,
        workspace_dir=tmp_path,
        session_id="test_session",
    )

    assert is_spilled is True
    assert meta is not None
    assert meta.total_chars == 120
    assert len(meta.sha256) == 64

    # Verify XML prompt block was injected
    assert isinstance(transformed, str)
    assert "<file_spillover path=" in transformed
    assert "payload_" in transformed

    # Check file exists in workspace
    expected_file = tmp_path / meta.file_path
    assert expected_file.exists()
    assert expected_file.read_text(encoding="utf-8") == query


def test_process_incoming_content_classmethod(tmp_path: Path) -> None:
    long_content = "Z" * 200
    res = ContextBombDefenseService.process_incoming_content(
        long_content,
        chat_id="chat_123",
        workspace_root=tmp_path,
        max_chars=100,
    )

    assert res.is_spilled is True
    assert res.original_char_count == 200
    assert res.spillover_path is not None
    assert Path(res.spillover_path).exists()
    assert "<file_spillover path=" in res.processed_content


def test_sweep_stale_spillover_files(tmp_path: Path) -> None:
    service = ContextBombDefenseService(max_chars=50, ttl_seconds=10)
    spill_dir = tmp_path / ".myrm/spillover"
    spill_dir.mkdir(parents=True, exist_ok=True)

    # Fresh file
    fresh = spill_dir / "payload_fresh.md"
    fresh.write_text("fresh")

    # Stale file
    stale = spill_dir / "payload_stale.md"
    stale.write_text("stale")
    past_time = time.time() - 200
    os.utime(stale, (past_time, past_time))

    purged = service.sweep_stale_spillover_files(workspace_dir=tmp_path, ttl_seconds=10)
    assert purged >= 1
    assert fresh.exists()
    assert not stale.exists()
