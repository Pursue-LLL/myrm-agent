"""Unit & service integration tests for ContextGuard in myrm-agent-server."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.agent.context_guard_service import ContextGuardService


@pytest.mark.asyncio
async def test_context_guard_service_normal_message() -> None:
    short_text = "This is a normal user message."
    res = await ContextGuardService.guard_inbound_prompt(
        chat_id="test_chat_1",
        raw_prompt=short_text,
    )
    assert res.spilled is False
    assert res.sanitized_content == short_text
    assert res.original_char_count == len(short_text)


@pytest.mark.asyncio
async def test_context_guard_service_oversized_message() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        with patch.object(ContextGuardService, "_resolve_base_dir", return_value=Path(tmp_dir)):
            oversized_text = "A" * 20_000
            res = await ContextGuardService.guard_inbound_prompt(
                chat_id="test_chat_2",
                raw_prompt=oversized_text,
            )
            assert res.spilled is True
            assert res.payload is not None
            assert Path(res.payload.file_path).exists()
            assert Path(res.payload.file_path).read_text(encoding="utf-8") == oversized_text
            assert "<file_spillover" in res.sanitized_content
            assert "chars=\"20000\"" in res.sanitized_content
            assert "read_file" in res.sanitized_content


def test_context_guard_sweep_all_workspaces() -> None:
    with tempfile.TemporaryDirectory() as tmp_root:
        root_path = Path(tmp_root)
        sub_workspace = root_path / "chat_123"
        sub_workspace.mkdir()

        spill_dir = sub_workspace / ".myrm/spillover"
        spill_dir.mkdir(parents=True)
        stale_file = spill_dir / "payload_old.md"
        stale_file.write_text("old text")

        # mock old mtime
        import os
        import time

        old_mtime = time.time() - 90000
        os.utime(stale_file, (old_mtime, old_mtime))

        cleaned = ContextGuardService.sweep_all_workspaces(root_dir=root_path)
        assert cleaned == 1
        assert not stale_file.exists()
