"""Prompt cache radar and cross-session cache efficiency aggregation.

[INPUT]
- sqlalchemy.ext.asyncio.AsyncSession (POS: 会话与聊天查询)
- app.config.settings::settings (POS: 日志路径配置)
- myrm_agent_harness.agent.event_log.backends.file_backend::FileEventLogBackend (POS: 事件日志读取)

[OUTPUT]
- get_prompt_cache_radar: API 端点，聚合近期会话的 Prompt Cache 命中率与节省额

[POS]
提取自 session_trace.py，负责全局跨会话 Prompt Cache 命中率分析与雷达指标聚合。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.core.utils.errors import internal_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.models import Chat

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/traces/prompt-cache-radar")
async def get_prompt_cache_radar(
    days: int = 7,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Aggregate Prompt Cache hit ratio and token savings across recent sessions."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 90)))
        stmt = (
            select(Chat)
            .where(Chat.updated_at >= cutoff)
            .order_by(Chat.updated_at.desc())
            .limit(100)
        )
        result = await db.execute(stmt)
        chats = result.scalars().all()

        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_cache_read_tokens = 0
        sessions_tracked = 0

        log_dir = Path(settings.database.event_log_dir)

        for chat in chats:
            chat_id = str(chat.id)
            log_file = log_dir / f"{chat_id}.jsonl"
            if not log_file.exists():
                continue

            try:
                has_session_tokens = False
                with open(log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            ev = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        ev_type = ev.get("type") or ev.get("event_type")
                        if ev_type in ("token_usage", "llm_end"):
                            data = ev.get("data") or {}
                            usage = data.get("usage") or data
                            if isinstance(usage, dict):
                                p = int(usage.get("prompt_tokens") or 0)
                                c = int(usage.get("completion_tokens") or 0)

                                cd = 0
                                if details := usage.get("prompt_tokens_details"):
                                    if isinstance(details, dict):
                                        cd = int(details.get("cached_tokens") or 0)
                                elif "cache_read_input_tokens" in usage:
                                    cd = int(usage.get("cache_read_input_tokens") or 0)

                                total_prompt_tokens += p
                                total_completion_tokens += c
                                total_cache_read_tokens += cd
                                has_session_tokens = True
                if has_session_tokens:
                    sessions_tracked += 1
            except Exception:
                pass

        fresh_input_tokens = max(0, total_prompt_tokens - total_cache_read_tokens)
        hit_ratio = (
            round(total_cache_read_tokens / total_prompt_tokens, 4)
            if total_prompt_tokens > 0
            else 0.0
        )
        estimated_savings_usd = round((total_cache_read_tokens / 1_000_000) * 0.42, 4)

        return success_response(
            data={
                "days": days,
                "sessions_tracked": sessions_tracked,
                "total_prompt_tokens": total_prompt_tokens,
                "fresh_input_tokens": fresh_input_tokens,
                "total_cache_read_tokens": total_cache_read_tokens,
                "total_completion_tokens": total_completion_tokens,
                "prompt_cache_hit_ratio": hit_ratio,
                "estimated_savings_usd": estimated_savings_usd,
            }
        )
    except Exception as e:
        raise internal_error(operation="Get prompt cache radar", exception=e) from e
