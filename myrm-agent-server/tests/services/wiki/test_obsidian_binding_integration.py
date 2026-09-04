"""Tests for Obsidian Vault binding, mtime delta scanning, inbox approval, and tools."""

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.wiki.portability.obsidian_tools import (
    create_obsidian_tools,
)

from app.api.approvals.obsidian_inbox import handle_obsidian_inbox_resolution
from app.database.models.approval import ApprovalRecord
from app.services.wiki.obsidian.binding import (
    ObsidianVaultBinding,
    scan_vault_mtime_watermark,
)


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


def test_obsidian_tools(tmp_path: Path):
    vault = tmp_path / "tool_vault"
    vault.mkdir()

    note = vault / "Project.md"
    note.write_text("# Project Alpha\nDetails about alpha release.", encoding="utf-8")

    canvas = vault / "Architecture.canvas"
    canvas.write_text(
        json.dumps({"nodes": [{"id": "1", "type": "text", "text": "Microservices Cluster Alpha"}]}),
        encoding="utf-8",
    )

    tools = create_obsidian_tools(lambda: str(vault))
    tool_map = {t.name: t for t in tools}

    assert "obsidian_vault_search" in tool_map
    assert "obsidian_vault_read" in tool_map
    assert "obsidian_inbox_write" in tool_map

    # Search
    search_res = tool_map["obsidian_vault_search"].invoke({"query": "Alpha"})
    assert "Project.md" in search_res or "Architecture.canvas" in search_res

    # Read
    read_res = tool_map["obsidian_vault_read"].invoke({"relative_path": "Project.md"})
    assert "Details about alpha release" in read_res


@pytest.mark.asyncio
async def test_handle_obsidian_inbox_resolution(tmp_path: Path):
    vault = tmp_path / "user_vault"
    vault.mkdir()

    mock_binding = ObsidianVaultBinding(
        vault_path=str(vault),
        is_active=True,
        allow_inbox_write=True,
        inbox_folder_name="_Myrm_Inbox",
    )

    record = ApprovalRecord(
        id="appr_test_123",
        action_type="obsidian_inbox_write",
        status="APPROVED",
        payload={
            "title": "Weekly_Summary",
            "content": "# Summary\nDone tasks.",
            "subfolder": "Summaries",
        },
    )

    with patch(
        "app.services.wiki.obsidian.binding.get_obsidian_vault_binding",
        AsyncMock(return_value=mock_binding),
    ):
        await handle_obsidian_inbox_resolution(record, "approve")

    target_file = vault / "_Myrm_Inbox" / "Summaries" / "Weekly_Summary.md"
    assert target_file.is_file()
    assert target_file.read_text(encoding="utf-8") == "# Summary\nDone tasks."
