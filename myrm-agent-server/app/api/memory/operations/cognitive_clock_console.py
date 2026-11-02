"""Cognitive clock console endpoints.

[INPUT]
- app.api.memory.operations.guardian::resolve_guardian_policy (POS: 守护者策略解析，含客户端时区初始化)
- app.lifecycle.cognitive_clock::get_clock_coordinator (POS: 多频率认知时钟协调器)
- app.lifecycle.cognitive_clock.executors::execute_t1_session_debounce (POS: T1 会话防抖整合)

[OUTPUT]
router: `GET /memory/guardian/cognitive-clock/status` nested clock status and
`POST /memory/guardian/cognitive-clock/trigger-t1` manual T1 consolidation.

[POS]
认知时钟控制台 API 操作层。只有 Memory Labs 的认知时钟面板调用这两个接口，因此只在 `MYRM_MEMORY_LABS=1` 时挂载；
前台活跃上报 `POST /guardian/cognitive-clock/activity` 由默认的聊天输入框调用，留在 `guardian.py`，对所有用户挂载。
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.api.memory.operations.guardian import resolve_guardian_policy

router = APIRouter(prefix="/guardian/cognitive-clock")


class CognitiveClockT1TriggerRequest(BaseModel):
    session_id: str


@router.get("/status")
async def get_cognitive_clock_status(request: Request) -> dict[str, object]:
    """Return nested multi-frequency cognitive clock status."""
    from app.lifecycle.cognitive_clock import get_clock_coordinator

    policy = await resolve_guardian_policy(request)
    coordinator = get_clock_coordinator()
    return await coordinator.get_status(policy=policy)


@router.post("/trigger-t1")
async def trigger_t1_session_debounce(body: CognitiveClockT1TriggerRequest) -> dict[str, object]:
    """Manually trigger T1 meso-session consolidation for a session."""
    from app.lifecycle.cognitive_clock.executors import execute_t1_session_debounce

    success = await execute_t1_session_debounce(session_id=body.session_id)
    return {"status": "ok" if success else "failed", "session_id": body.session_id}
