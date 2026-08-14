"""Chat usage cache rebuild orchestration.

[INPUT]
- usage_cache::ChatUsageCache (POS: 进程内 TTL 去抖缓存)
- statistics.usage_aggregation::aggregate_chat_usage_rows (POS: 消息级聚合纯函数)
- _base::_ChatServiceBase (POS: repository 访问器)

[OUTPUT]
- sync_chat_usage (POS: Chat.total_* 用量缓存重建入口，供消息落库与轮次突变点复用)

[POS]
用量缓存重建编排层。The Chat.total_* columns are an O(1) usage cache rebuilt
from assistant message tokenEconomics snapshots. This module owns the rebuild:
reading the active assistant messages, aggregating them, and overwriting the
chat columns with a TTL-debounced cache keyed on the last aggregated message
id. Both message persistence and turn mutations reuse this single entry point.
"""

from __future__ import annotations

import logging

from app.database.repositories.uow import UnitOfWork

from ._base import _ChatServiceBase
from .usage_cache import ChatUsageCache

logger = logging.getLogger(__name__)

_chat_usage_cache = ChatUsageCache()


async def sync_chat_usage(chat_id: str) -> None:
    """Rebuild Chat.total_calls/total_tokens/total_usd from assistant messages.

    Aggregates the ``tokenEconomics`` snapshots persisted on assistant message
    rows and overwrites the chat usage cache columns. The aggregation result is
    cached with the last aggregated message id so consecutive turns within the
    TTL window reuse the aggregate while a new or sibling-switched message
    forces a rebuild. Best-effort: failures are logged and never break the
    caller (the cache is rebuilt lazily on the next sync).
    """
    from app.core.utils.session_id import is_safe_session_id
    from app.services.statistics.usage_aggregation import aggregate_chat_usage_rows

    if not is_safe_session_id(chat_id):
        return
    try:
        async with UnitOfWork() as uow:
            extras, last_message_id = await _ChatServiceBase._cr(uow).get_assistant_extra_data(chat_id)
        cached = _chat_usage_cache.get(chat_id, last_message_id)
        if cached is not None:
            usage_updates = cached
        else:
            usage_updates = aggregate_chat_usage_rows(extras)
            _chat_usage_cache.set(chat_id, last_message_id, usage_updates)
        async with UnitOfWork() as uow:
            await _ChatServiceBase._cr(uow).update_chat_fields(chat_id, usage_updates)
    except Exception as err:
        logger.error(f"Failed to sync usage ledger to DB for chat {chat_id}: {err}")
