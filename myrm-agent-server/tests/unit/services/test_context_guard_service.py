from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.context_guard_service import ContextGuardService


@pytest.mark.asyncio
async def test_guard_inbound_prompt_under_threshold() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.object(ContextGuardService, "_resolve_base_dir", new=AsyncMock(return_value=Path(tmpdir))):
            short_prompt = "Explain quantum computing in simple terms."
            result = await ContextGuardService.guard_inbound_prompt(
                chat_id="test_chat_1",
                raw_prompt=short_prompt,
            )
            assert result.spilled is False
            assert result.sanitized_content == short_prompt
            assert result.payload is None


@pytest.mark.asyncio
async def test_guard_inbound_prompt_over_threshold_creates_file() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.object(ContextGuardService, "_resolve_base_dir", new=AsyncMock(return_value=Path(tmpdir))):
            # Create a 20,000 character prompt
            long_prompt = "Large log entry: " + "X" * 20_000
            result = await ContextGuardService.guard_inbound_prompt(
                chat_id="test_chat_2",
                raw_prompt=long_prompt,
            )
            assert result.spilled is True
            assert result.payload is not None
            assert Path(result.payload.file_path).exists()
            assert "<file_spillover" in result.sanitized_content
            assert result.payload.sha256_digest[:16] in result.sanitized_content
            assert Path(result.payload.file_path).read_text(encoding="utf-8") == long_prompt


def test_sweep_all_workspaces_cleans_stale_files() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root_path = Path(tmpdir)
        chat_ws = root_path / "chat_123" / ".myrm" / "spillover"
        chat_ws.mkdir(parents=True, exist_ok=True)

        stale_file = chat_ws / "payload_old.md"
        stale_file.write_text("old content", encoding="utf-8")

        # Mock mtime to 48 hours ago
        import os
        import time

        past_time = time.time() - (48 * 3600)
        os.utime(stale_file, (past_time, past_time))

        cleaned = ContextGuardService.sweep_all_workspaces(root_dir=root_path)
        assert cleaned >= 1
        assert not stale_file.exists()
