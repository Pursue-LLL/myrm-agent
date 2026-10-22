"""无人值守与多渠道运行事件日志覆盖状态与健康检查 API.

[INPUT]
- event_log_dir 路径扫描
- 注入器配置状态与会话标识校验请求

[OUTPUT]
- GET /summary: 获取定时任务、IM 渠道、目标触发与语音入口的覆盖状态与分片健康汇总
- POST /validate: 验证指定入口生成的会话标识是否符合安全白名单与按日分片规则
- GET /shards: 按入口前缀聚合当前磁盘上的事件日志分片统计

[POS]
app/api/system/ 运维与系统监控端点。为无人值守与渠道运行提供事件日志覆盖度感知，
消除统计与成长看板系统性漏计问题。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.ai_agents.event_log_injector import (
    get_default_event_log_config,
    resolve_cron_event_log_session_id,
    resolve_voice_realtime_session_id,
    sanitize_channel_event_log_session_id,
)
from app.core.utils.session_id import is_safe_session_id

router = APIRouter(prefix="/event-log-coverage", tags=["EventLogCoverage"])


class EntrypointCoverageSpec(BaseModel):
    """单入口事件日志覆盖策略规范."""

    entrypoint: Literal["cron", "channel", "goal", "voice", "voice_realtime", "web_chat"] = Field(
        ..., description="入口类型"
    )
    is_injected: bool = Field(True, description="是否已接入事件日志统一注入器")
    strategy_desc: str = Field(..., description="分片与隔离策略说明")
    sample_session_id: str = Field(..., description="示例生成的会话标识")
    is_safe: bool = Field(True, description="示例会话标识是否通过路径安全白名单")


class ShardSummary(BaseModel):
    """日志分片统计."""

    prefix: str = Field(..., description="会话前缀 (cron / channel / goal / voice / chat)")
    file_count: int = Field(0, description="分片文件总数")
    total_bytes: int = Field(0, description="分片文件总字节数")


class CoverageSummaryResponse(BaseModel):
    """覆盖状态与健康度汇总响应."""

    event_log_dir: str | None = Field(None, description="事件日志根目录")
    max_line_bytes: int | None = Field(None, description="单行最大字节数阈值")
    is_directory_configured: bool = Field(..., description="日志目录是否已配置")
    entrypoints: list[EntrypointCoverageSpec] = Field(default_factory=list, description="全部入口覆盖策略")
    anti_growth_protection: bool = Field(True, description="是否已启用按日分片与防无限增长保护")
    shards: list[ShardSummary] = Field(default_factory=list, description="当前磁盘分片分类统计")


class ValidateSessionIdRequest(BaseModel):
    """校验会话标识请求."""

    entrypoint: Literal["cron", "channel", "goal", "voice", "voice_realtime"] = Field(
        ..., description="目标入口"
    )
    raw_identifier: str = Field(..., description="原始输入标识或任务ID")


class ValidateSessionIdResponse(BaseModel):
    """校验会话标识响应."""

    entrypoint: str
    resolved_session_id: str
    is_safe: bool
    is_daily_sharded: bool


@router.get("/summary", response_model=CoverageSummaryResponse)
async def get_coverage_summary() -> CoverageSummaryResponse:
    """获取所有入口的事件日志覆盖状态与磁盘分片分布."""
    log_dir_str, max_line_bytes = get_default_event_log_config()
    is_configured = bool(log_dir_str)

    cron_sample = resolve_cron_event_log_session_id("nightly_backup")
    voice_rt_sample = resolve_voice_realtime_session_id(None)
    channel_sample = sanitize_channel_event_log_session_id("tg_group_987", default_prefix="channel_telegram")
    goal_sample = sanitize_channel_event_log_session_id("autonomous_audit", default_prefix="goal")

    specs: list[EntrypointCoverageSpec] = [
        EntrypointCoverageSpec(
            entrypoint="cron",
            is_injected=True,
            strategy_desc="独立运行按日分片 (cron:{job_id}:{date})，主会话复用 chat_id",
            sample_session_id=cron_sample,
            is_safe=is_safe_session_id(cron_sample),
        ),
        EntrypointCoverageSpec(
            entrypoint="channel",
            is_injected=True,
            strategy_desc="安全白名单清洗与渠道前缀绑定 (channel_{name}:{id})",
            sample_session_id=channel_sample,
            is_safe=is_safe_session_id(channel_sample),
        ),
        EntrypointCoverageSpec(
            entrypoint="goal",
            is_injected=True,
            strategy_desc="目标会话透传与安全隔离 (goal:{id})",
            sample_session_id=goal_sample,
            is_safe=is_safe_session_id(goal_sample),
        ),
        EntrypointCoverageSpec(
            entrypoint="voice",
            is_injected=True,
            strategy_desc="语音 Bridge 规范前缀与安全会话透传",
            sample_session_id="voice:chat_session_001",
            is_safe=is_safe_session_id("voice:chat_session_001"),
        ),
        EntrypointCoverageSpec(
            entrypoint="voice_realtime",
            is_injected=True,
            strategy_desc="实时工具执行按日分片 (voice:realtime:{date})，防单文件无限追加",
            sample_session_id=voice_rt_sample,
            is_safe=is_safe_session_id(voice_rt_sample),
        ),
        EntrypointCoverageSpec(
            entrypoint="web_chat",
            is_injected=True,
            strategy_desc="对话入口原生注入与安全校验",
            sample_session_id="chat-123e4567-e89b",
            is_safe=is_safe_session_id("chat-123e4567-e89b"),
        ),
    ]

    shards_map: dict[str, ShardSummary] = {
        "cron": ShardSummary(prefix="cron", file_count=0, total_bytes=0),
        "channel": ShardSummary(prefix="channel", file_count=0, total_bytes=0),
        "goal": ShardSummary(prefix="goal", file_count=0, total_bytes=0),
        "voice": ShardSummary(prefix="voice", file_count=0, total_bytes=0),
        "web": ShardSummary(prefix="web", file_count=0, total_bytes=0),
    }

    if is_configured and log_dir_str:
        p = Path(log_dir_str)
        if p.exists() and p.is_dir():
            for f in p.glob("*.jsonl"):
                stem = f.stem
                matched_prefix = "web"
                for prefix in ("cron", "channel", "goal", "voice"):
                    if stem.startswith(prefix):
                        matched_prefix = prefix
                        break
                size = f.stat().st_size
                shards_map[matched_prefix].file_count += 1
                shards_map[matched_prefix].total_bytes += size

    return CoverageSummaryResponse(
        event_log_dir=log_dir_str,
        max_line_bytes=max_line_bytes,
        is_directory_configured=is_configured,
        entrypoints=specs,
        anti_growth_protection=True,
        shards=list(shards_map.values()),
    )


@router.post("/validate", response_model=ValidateSessionIdResponse)
async def validate_session_id(req: ValidateSessionIdRequest) -> ValidateSessionIdResponse:
    """验证传入入口生成的会话标识安全性与分片有效性."""
    target_id = ""
    is_daily = False

    import re

    if req.entrypoint == "cron":
        target_id = resolve_cron_event_log_session_id(req.raw_identifier)
        is_daily = bool(re.search(r":\d{4}-\d{2}-\d{2}$", target_id))
    elif req.entrypoint == "voice_realtime":
        target_id = resolve_voice_realtime_session_id(req.raw_identifier)
        is_daily = bool(re.search(r":\d{4}-\d{2}-\d{2}$", target_id))
    elif req.entrypoint == "channel":
        target_id = sanitize_channel_event_log_session_id(req.raw_identifier, "channel")
    elif req.entrypoint == "goal":
        target_id = sanitize_channel_event_log_session_id(req.raw_identifier, "goal")
    else:
        target_id = sanitize_channel_event_log_session_id(req.raw_identifier, "voice")

    return ValidateSessionIdResponse(
        entrypoint=req.entrypoint,
        resolved_session_id=target_id,
        is_safe=is_safe_session_id(target_id),
        is_daily_sharded=is_daily,
    )


__all__ = ["router"]
