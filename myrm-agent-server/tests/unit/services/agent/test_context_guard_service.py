from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.context_guard_service import ContextGuardService


@pytest.mark.asyncio
async def test_context_guard_service_short_prompt() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.object(ContextGuardService, "_resolve_base_dir", new=AsyncMock(return_value=Path(tmpdir))):
            res = await ContextGuardService.guard_inbound_prompt(
                chat_id="test_chat",
                raw_prompt="Short user query",
            )
            assert res.is_spilled is False
            assert res.processed_content == "Short user query"
            assert res.spillover_path is None


@pytest.mark.asyncio
async def test_context_guard_service_oversized_prompt() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.object(ContextGuardService, "_resolve_base_dir", new=AsyncMock(return_value=Path(tmpdir))):
            # 20k characters to exceed 16k chars cap
            oversized_content = "X" * 20_000
            res = await ContextGuardService.guard_inbound_prompt(
                chat_id="test_chat",
                raw_prompt=oversized_content,
            )
            assert res.is_spilled is True
            assert Path(res.spillover_path).exists()
            assert Path(res.spillover_path).read_text(encoding="utf-8") == oversized_content
            assert "<file_spillover" in res.processed_content
            assert res.content_sha256[:16] in res.processed_content
            assert res.relative_path in res.processed_content


def test_context_guard_service_sweep_workspaces() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root_dir = Path(tmpdir)
        chat_ws = root_dir / "chat_123"
        spill_dir = chat_ws / ".myrm/spillover"
        spill_dir.mkdir(parents=True, exist_ok=True)

        expired_file = spill_dir / "expired_payload.md"
        expired_file.write_text("old text")

        # Set old mtime (2 days ago)
        import os
        import time

        old_time = time.time() - 172_800
        os.utime(expired_file, (old_time, old_time))

        cleaned = ContextGuardService.sweep_all_workspaces(root_dir=root_dir)
        assert cleaned == 1
        assert not expired_file.exists()
