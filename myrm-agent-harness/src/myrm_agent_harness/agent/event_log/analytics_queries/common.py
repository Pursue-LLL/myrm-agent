"""[INPUT]
- .types::StructuredEvent (POS: 事件类型)

[OUTPUT]
- _collect_events / _durations / _failure_reasons: 查询共用的事件收集与字段提取

[POS]
`event_log/analytics_queries/` 的共享助手；不包含任何具体查询。
"""

from __future__ import annotations

from collections import Counter
from collections.abc import AsyncIterable
from typing import TYPE_CHECKING, Any, cast

from ..types import StructuredEvent

if TYPE_CHECKING:
    pass

async def _collect_events(result: object) -> list[StructuredEvent]:
    from collections.abc import Awaitable

    if isinstance(result, list):
        return result
    if isinstance(result, AsyncIterable):
        return [event async for event in result]
    return list(await cast(Awaitable[Any], result))

def _durations(data: dict[str, object]) -> list[float]:
    values = data.get("durations")
    return values if isinstance(values, list) else []

def _failure_reasons(data: dict[str, object]) -> Counter[str]:
    values = data.get("failure_reasons")
    return values if isinstance(values, Counter) else Counter()
