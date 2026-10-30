"""
[INPUT]
- (标准库) asyncio / functools / weakref
[OUTPUT]
- serialized_per_evolution: 同一条提案的决议函数同一时刻只运行一个（按第一个位置参数 evolution_id 加锁）
[POS]
Evolution 审核决议串行化。批准、拒绝、修订、回滚都是「读记录 → 落盘或改写 → 整条写回」，写回是无条件覆盖：
两个决议交错时，后写入的会把先写入的结果整个盖掉（批准落盘的同时被拒绝改写成已拒绝，文件已改而记录显示未应用）。
串行之后，后到的决议读到的就是先到的决议的最终结果，按现有的状态判断自行放行或以 409 拒绝。
这是进程内锁，成立的前提是服务端单进程（`app/main.py` 以单个 uvicorn 进程运行）；改为多 worker 时须换成数据库层的条件更新。
"""

from __future__ import annotations

import asyncio
import functools
import weakref
from collections.abc import Awaitable, Callable
from typing import Concatenate, ParamSpec, TypeVar

_P = ParamSpec("_P")
_R = TypeVar("_R")

# One lock per proposal, alive only while a request holds or awaits it.
_DECISION_LOCKS: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()


def serialized_per_evolution(
    action: Callable[Concatenate[str, _P], Awaitable[_R]],
) -> Callable[Concatenate[str, _P], Awaitable[_R]]:
    """Run ``action`` one call at a time per evolution id (its first positional argument)."""

    @functools.wraps(action)
    async def serialized(evolution_id: str, /, *args: _P.args, **kwargs: _P.kwargs) -> _R:
        async with _DECISION_LOCKS.setdefault(evolution_id, asyncio.Lock()):
            return await action(evolution_id, *args, **kwargs)

    return serialized
