"""
[INPUT]
- (标准库) asyncio / functools / weakref
[OUTPUT]
- serialized_per_evolution: 同一条提案的 payload 写入函数同一时刻只运行一个（按第一个位置参数 evolution_id 加锁）
[POS]
Evolution 审核记录写入串行化。批准、拒绝、修订、回滚与运行时失败计数更新都是「读记录 → 落盘或改写 → 整条写回」，
写回是无条件覆盖（`persist_approval_payload` 不比对读到的版本）：两次写入交错时，后写入的会把先写入的结果整个盖掉。
批准落盘的同时被拒绝：拒绝返回已拒绝，终态却是已批准且已应用，账本依次是待审、已拒绝、已批准，文件已写入；
计数更新读到批准前的 payload，批准应用完成后它再写回，`apply_status` 退回未应用，回滚随之不可用。
串行之后，后到的写入读到的就是先到者的最终结果，按现有的状态判断自行放行或以 409 拒绝。
这是进程内锁，成立的前提是服务端单进程：`run.py` 默认以单个 uvicorn 进程启动，直接运行 `app/main.py` 同样是单个 uvicorn。
`SERVER_MODE=granian`（多 worker）是可选项，不适用于内嵌数据库，不在支持范围内；改为多 worker 时须换成数据库层的条件更新。
"""

from __future__ import annotations

import asyncio
import functools
import weakref
from collections.abc import Awaitable, Callable, Coroutine
from typing import Concatenate, ParamSpec, TypeVar

_P = ParamSpec("_P")
_R = TypeVar("_R")

# One lock per proposal, alive only while a request holds or awaits it.
_DECISION_LOCKS: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()


def serialized_per_evolution(
    action: Callable[Concatenate[str, _P], Awaitable[_R]],
) -> Callable[Concatenate[str, _P], Coroutine[None, None, _R]]:
    """Run ``action`` one call at a time per evolution id (its first positional argument)."""

    @functools.wraps(action)
    async def serialized(evolution_id: str, /, *args: _P.args, **kwargs: _P.kwargs) -> _R:
        async with _DECISION_LOCKS.setdefault(evolution_id, asyncio.Lock()):
            return await action(evolution_id, *args, **kwargs)

    return serialized
