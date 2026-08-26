"""Cross-Session Trajectory API — Extract and structure multi-turn tool execution traces.

[INPUT]
- fastapi::APIRouter, Depends, HTTPException
- app.services.chat.chat_service::ChatService
- app.database.connection::get_db

[OUTPUT]
- router: Mounted under /chats/{chat_id}/trajectory
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.services.chat.chat_service import ChatService

router = APIRouter()


class TrajectoryStep(BaseModel):
    step_index: int
    tool_name: str
    tool_args: dict[str, Any] = Field(default_factory=dict)
    tool_result_summary: str | None = None
    is_error: bool = False
    duration_ms: float = 0.0
    tokens_used: int = 0


class TurnTrajectory(BaseModel):
    turn_id: str
    user_prompt: str
    assistant_reply: str | None = None
    steps: list[TrajectoryStep] = Field(default_factory=list)
    total_steps: int = 0
    total_tokens: int = 0
    created_at: str | None = None


class SessionTrajectoryResponse(BaseModel):
    session_id: str
    title: str | None = None
    turns: list[TurnTrajectory] = Field(default_factory=list)
    total_turns: int = 0
    total_tool_calls: int = 0
    total_tokens: int = 0


@router.get("/{chat_id}/trajectory", response_model=SessionTrajectoryResponse)
async def get_session_trajectory(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
) -> SessionTrajectoryResponse:
    """Extract ordered execution trajectory with all tool steps for a chat session."""
    chat = await ChatService.get_chat_metadata(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat session not found")

    messages, _ = await ChatService.get_messages_paginated(chat_id, limit=200)

    turns: list[TurnTrajectory] = []
    curr_user_msg: str | None = None
    curr_turn_id: str | None = None
    curr_created_at: str | None = None

    for msg in messages:
        if msg.role == "user":
            curr_user_msg = msg.content
            curr_turn_id = msg.id
            curr_created_at = msg.created_at.isoformat() if hasattr(msg.created_at, "isoformat") else str(msg.created_at)
        elif msg.role == "assistant" and curr_user_msg is not None:
            extra = msg.extra_data or {}
            raw_steps = extra.get("tasks_steps") or extra.get("tool_calls") or []
            
            steps: list[TrajectoryStep] = []
            for idx, raw in enumerate(raw_steps):
                if isinstance(raw, dict):
                    t_name = str(raw.get("tool_name") or raw.get("name") or "unknown_tool")
                    t_args = raw.get("arguments") or raw.get("args") or {}
                    if not isinstance(t_args, dict):
                        t_args = {"raw": str(t_args)}
                    t_res = raw.get("result") or raw.get("output") or raw.get("error")
                    steps.append(
                        TrajectoryStep(
                            step_index=idx + 1,
                            tool_name=t_name,
                            tool_args=t_args,
                            tool_result_summary=str(t_res)[:300] if t_res else None,
                            is_error=bool(raw.get("is_error") or raw.get("error")),
                            duration_ms=float(raw.get("duration_ms") or 0.0),
                            tokens_used=int(raw.get("tokens") or 0),
                        )
                    )

            turn_tokens = int(extra.get("token_usage") or extra.get("total_tokens") or 0)
            turns.append(
                TurnTrajectory(
                    turn_id=curr_turn_id or msg.id,
                    user_prompt=curr_user_msg,
                    assistant_reply=msg.content[:500] if msg.content else None,
                    steps=steps,
                    total_steps=len(steps),
                    total_tokens=turn_tokens,
                    created_at=curr_created_at,
                )
            )
            curr_user_msg = None
            curr_turn_id = None

    total_calls = sum(len(t.steps) for t in turns)
    total_tokens = sum(t.total_tokens for t in turns)

    return SessionTrajectoryResponse(
        session_id=chat_id,
        title=getattr(chat, "title", None) or getattr(chat, "name", None),
        turns=turns,
        total_turns=len(turns),
        total_tool_calls=total_calls,
        total_tokens=total_tokens,
    )
