"""[INPUT]
- pydantic::{BaseModel, Field}
- fastapi::{APIRouter, Path}

[OUTPUT]
- router: APIRouter 实例，包含 /{chat_id}/stop-thinking 接口
- StopThinkingRequest, StopThinkingResponse

[POS]
app/api/chats/chat/thought_control.py — 提供思考链提前收敛与主动停止干预控制端点。
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Path
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chats-thought-control"])


class StopThinkingRequest(BaseModel):
    """停止思考请求。"""

    reason: str = Field("user_interrupted", description="中断思考原因标识")
    force_immediate_answer: bool = Field(True, description="是否要求模型立即进入回答生成阶段")


class StopThinkingResponse(BaseModel):
    """停止思考响应。"""

    success: bool
    chat_id: str
    message: str


# 进程内会话提前收敛信号标记集合
_STOP_THINKING_SIGNALS: set[str] = set()


def is_thought_stopped(chat_id: str) -> bool:
    """查询指定会话是否已触发停止思考信号。"""
    return chat_id in _STOP_THINKING_SIGNALS


def clear_thought_signal(chat_id: str) -> None:
    """清理会话停止思考信号。"""
    _STOP_THINKING_SIGNALS.discard(chat_id)


@router.post(
    "/{chat_id}/stop-thinking",
    response_model=StopThinkingResponse,
    summary="提前终止当前对话的思考链推演并促使其直接输出回答",
)
async def stop_thinking(
    chat_id: Annotated[str, Path(description="对话唯一 ID")],
    payload: StopThinkingRequest | None = None,
) -> StopThinkingResponse:
    """通知正在运行的长思考模型提前收敛思维流，遏制无限死循环或超长思考，直接转入最终作答。"""
    reason = payload.reason if payload else "user_interrupted"
    logger.info("Early thought convergence signal triggered for chat %s (reason: %s)", chat_id, reason)

    _STOP_THINKING_SIGNALS.add(chat_id)

    return StopThinkingResponse(
        success=True,
        chat_id=chat_id,
        message="思考链已接收提前收敛信号，正在转入输出回答阶段。",
    )
