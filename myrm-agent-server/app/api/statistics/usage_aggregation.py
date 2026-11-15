"""Usage aggregation re-export facade.

[INPUT]
app.services.statistics.usage_aggregation (POS: 用量聚合纯逻辑)

[OUTPUT]
app.api.statistics.* (POS: HTTP 统计路由与装配)

[POS]
API 层入口。纯聚合逻辑在 services 层，本模块仅 re-export，
供 API 路由、脚本与测试按 app.api.statistics 的 import 路径使用。
"""

from app.services.statistics.usage_aggregation import (
    DayAccumulator,
    TierAccumulator,
    aggregate_chat_usage_rows,
    aggregate_usage,
    build_stream_ttft_summary,
    compute_estimated_savings,
    extract_stream_ttft_ms,
    extract_usage,
    normalize_tier,
    normalize_usage_rows,
    to_float,
    to_int,
)

__all__ = [
    "DayAccumulator",
    "TierAccumulator",
    "aggregate_chat_usage_rows",
    "aggregate_usage",
    "compute_estimated_savings",
    "build_stream_ttft_summary",
    "extract_stream_ttft_ms",
    "extract_usage",
    "normalize_tier",
    "normalize_usage_rows",
    "to_float",
    "to_int",
]
