"""Archived compaction backup retrieval.

[INPUT]
- app.platform_utils::get_storage_provider (POS: 平台存储抽象)

[OUTPUT]
- get_archived_messages: Retrieve deduplicated archived messages from backup files

[POS]
从 workspace 备份文件恢复被 compact 截断的历史消息。
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


async def get_archived_messages(chat_id: str) -> list[dict[str, object]]:
    """Retrieve all archived messages from the workspace backup files."""
    try:
        from app.platform_utils import get_storage_provider

        storage = get_storage_provider()
        prefix = f".myrm/chat_backups/{chat_id}/"

        files = await storage.list(prefix=prefix, recursive=False)

        all_messages: list[dict[str, object]] = []
        for file_path in sorted(files):
            content = await storage.read(file_path)
            if not content:
                continue
            lines = content.decode("utf-8").splitlines()
            for line in lines:
                if not line.strip():
                    continue
                try:
                    data_raw = json.loads(line)
                    if not isinstance(data_raw, dict):
                        continue
                    data: dict[str, object] = {str(k): v for k, v in data_raw.items()}
                    if data.get("type") == "previous_summary":
                        continue
                    all_messages.append(data)
                except Exception:
                    pass

        seen_ids: set[object] = set()
        unique_messages: list[dict[str, object]] = []
        for msg in all_messages:
            msg_id = msg.get("id")
            if msg_id and msg_id not in seen_ids:
                seen_ids.add(msg_id)
                unique_messages.append(msg)

        return unique_messages
    except Exception as exc:
        logger.warning(
            "Failed to retrieve archived messages for chat %s: %s", chat_id, exc
        )
        return []
