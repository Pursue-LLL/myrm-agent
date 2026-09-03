"""Obsidian Inbox approval resolution handler.

[INPUT]
- app.database.models.approval::ApprovalRecord
- app.services.wiki.obsidian.binding::get_obsidian_vault_binding

[OUTPUT]
- handle_obsidian_inbox_resolution: Writes approved markdown note to the bound Obsidian Vault inbox folder.

[POS]
Approval resolution handler for Obsidian write-back. Ensures agent-generated documents
never write directly to user vaults without explicit user approval.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.database.models.approval import ApprovalRecord

logger = logging.getLogger(__name__)


async def handle_obsidian_inbox_resolution(record: ApprovalRecord, decision: str) -> None:
    """Write approved markdown content to the user's bound Obsidian Vault inbox folder."""
    if decision != "approve":
        logger.info("Obsidian inbox write %s rejected by user", record.id)
        return

    from app.services.wiki.obsidian.binding import get_obsidian_vault_binding

    binding = await get_obsidian_vault_binding()
    if not binding or not binding.is_active or not binding.vault_path:
        logger.error("Cannot resolve Obsidian inbox write %s: no active vault bound", record.id)
        return

    if not binding.allow_inbox_write:
        logger.error("Obsidian inbox write %s rejected: allow_inbox_write is disabled", record.id)
        return

    payload = record.payload or {}
    title = str(payload.get("title", "")).strip() or "Agent_Note"
    content = str(payload.get("content", "")).strip()
    subfolder = str(payload.get("subfolder", "")).strip()

    vault_root = Path(binding.vault_path)
    if not vault_root.is_dir():
        logger.error("Obsidian vault directory not found: %s", binding.vault_path)
        return

    inbox_folder_name = binding.inbox_folder_name.strip() or "_Myrm_Inbox"
    inbox_dir = vault_root / inbox_folder_name
    if subfolder:
        # Prevent directory traversal
        clean_subfolder = re.sub(r"\.\.+", "", subfolder).strip("/\\")
        inbox_dir = inbox_dir / clean_subfolder

    inbox_dir.mkdir(parents=True, exist_ok=True)

    safe_title = re.sub(r'[\\/*?:"<>|]+', "_", title).strip() or "Note"
    if not safe_title.endswith(".md"):
        safe_title += ".md"

    target_file = inbox_dir / safe_title
    counter = 1
    stem = target_file.stem
    while target_file.exists():
        target_file = inbox_dir / f"{stem}_{counter}.md"
        counter += 1

    try:
        target_file.write_text(content, encoding="utf-8")
        logger.info("Successfully wrote approved Obsidian note to %s", target_file)
    except OSError as exc:
        logger.error("Failed to write approved Obsidian note to %s: %s", target_file, exc)
