"""[INPUT]
- typing::{Annotated}
- fastapi::{APIRouter, HTTPException, Path, status}
- app.core.infra.health.multi_tier_health::{get_multi_tier_checker, MultiTierHealthReport}

[OUTPUT]
- router: APIRouter for multi-tier health checks and causal trace retrieval
- record_trace_tree: 辅助记录因果 Trace 树到内存/持久化

[POS]
app/api/system/multi_tier_health_api.py — 分层健康检查与因果 TraceSpan 树查询端点。
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, status

from app.core.infra.health.multi_tier_health import (
    MultiTierHealthReport,
    get_multi_tier_checker,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system-multi-tier-health"])

# 内存保留近期的因果 Trace 字典（上限 200 条）
_TRACE_CACHE: dict[str, dict[str, object]] = {}
_MAX_TRACE_CACHE_SIZE = 200


def record_trace_tree(trace_id: str, trace_dict: dict[str, object]) -> None:
    """写入因果 Trace 到近期缓存。"""
    if len(_TRACE_CACHE) >= _MAX_TRACE_CACHE_SIZE:
        # 淘汰最早的一半条目
        keys_to_remove = list(_TRACE_CACHE.keys())[:100]
        for k in keys_to_remove:
            _TRACE_CACHE.pop(k, None)
    _TRACE_CACHE[trace_id] = trace_dict


@router.get(
    "/health/multi-tier",
    response_model=MultiTierHealthReport,
    summary="分层巡检组件层与入口网关层能力健康状态",
)
async def get_multi_tier_health() -> MultiTierHealthReport:
    """超越单一进程存活，分层评估 SQLite、向量库、工具沙箱与网络通道真实可用性。"""
    checker = get_multi_tier_checker()
    return await checker.check_all()


@router.get(
    "/traces/{trace_id}",
    summary="获取指定会话请求的因果 TraceSpan 树全景",
)
async def get_trace_tree_endpoint(
    trace_id: Annotated[str, Path(description="请求 Trace 唯一标识符")],
) -> dict[str, object]:
    """查询单次 Agent 请求的完整因果调用树，包含各阶段耗时、Token 与脱敏参数。"""
    trace_data = _TRACE_CACHE.get(trace_id)
    if not trace_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trace with ID '{trace_id}' not found.",
        )
    return trace_data
