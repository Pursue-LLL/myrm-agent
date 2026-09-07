from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.services.agent.context_guard_service import ContextGuardService


@pytest.mark.asyncio
async def test_context_guard_service_under_threshold() -> None:
    short_prompt = "Hello AI, write a quick summary of Python."
    result = await ContextGuardService.guard_inbound_prompt(
        chat_id="test_chat_short",
        raw_prompt=short_prompt,
    )
    assert not result.spilled
    assert result.sanitized_content == short_prompt
    assert result.original_char_count == len(short_prompt)


@pytest.mark.asyncio
async def test_context_guard_service_spillover_overflow() -> None:
    with tempfile.TemporaryDirectory():
        # Create a large prompt exceeding 16,000 characters
        large_prompt = "Critical system logs:\n" + (
            "ERROR 500: Database connection timed out.\n" * 400
        )
        assert len(large_prompt) > 16_000

        result = await ContextGuardService.guard_inbound_prompt(
            chat_id="test_chat_overflow",
            raw_prompt=large_prompt,
        )

        assert result.spilled is True
        assert result.payload is not None
        assert result.original_char_count == len(large_prompt)
        assert "<file_spillover" in result.sanitized_content
        assert "payload" in result.sanitized_content
        assert Path(result.payload.file_path).exists()
        assert (
            Path(result.payload.file_path).read_text(encoding="utf-8") == large_prompt
        )


def test_context_guard_service_sweep_workspaces() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root_path = Path(tmpdir)
        chat_dir = root_path / "chat_123"
        spillover_dir = chat_dir / ".myrm/spillover"
        spillover_dir.mkdir(parents=True, exist_ok=True)

        expired_file = spillover_dir / "payload_old.md"
        expired_file.write_text("old logs", encoding="utf-8")

        # Mock mtime 2 days ago
        past_time = 1000.0
        import os

        os.utime(expired_file, (past_time, past_time))

        cleaned = ContextGuardService.sweep_all_workspaces(root_dir=root_path)
        assert cleaned == 1
        assert not expired_file.exists()
