#!/usr/bin/env python3
"""One-off backfill of Chat.total_calls/total_tokens/total_usd from message extra_data.

Before the message-level usage sync in chat_message.py, the Chat usage cache
was only refreshed from the event_log ``session_end`` snapshot, which is never
emitted under POOLED sessions and is lost on crashes. This script rebuilds the
cache for chats whose totals are stale (zero or diverging from the
message-derived aggregate).

Usage:
    uv run python scripts/dev/backfill-chat-usage.py [--force]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select  # noqa: E402

from app.api.statistics.usage_aggregation import aggregate_chat_usage_rows  # noqa: E402
from app.database.connection import get_session  # noqa: E402
from app.database.models import Chat  # noqa: E402
from app.database.repositories.chat_repo import ChatRepository  # noqa: E402


def _is_stale(chat: Chat, aggregated: dict[str, int | float]) -> bool:
    if chat.total_calls != aggregated["total_calls"]:
        return True
    if chat.total_tokens != aggregated["total_tokens"]:
        return True
    return abs(float(chat.total_usd) - float(aggregated["total_usd"])) > 1e-6


async def backfill(force: bool, limit: int) -> None:
    processed = 0
    updated = 0
    async with get_session() as db:
        result = await db.execute(select(Chat))
        chats = result.scalars().all()
        for chat in chats:
            if limit and processed >= limit:
                break
            processed += 1
            extras = await ChatRepository.get_assistant_extra_data(db, chat.id)
            aggregated = aggregate_chat_usage_rows(extras)
            if force or _is_stale(chat, aggregated):
                await ChatRepository.update_chat_fields(db, chat.id, aggregated)
                updated += 1
                print(
                    f"  {chat.id}: calls={aggregated['total_calls']} "
                    f"tokens={aggregated['total_tokens']} usd={aggregated['total_usd']}"
                )
        await db.commit()
    print(f"processed={processed} updated={updated}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild Chat usage cache from messages")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rewrite every chat, not only stale ones",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process at most N chats (0 = all)",
    )
    args = parser.parse_args()
    asyncio.run(backfill(force=args.force, limit=args.limit))


if __name__ == "__main__":
    main()
