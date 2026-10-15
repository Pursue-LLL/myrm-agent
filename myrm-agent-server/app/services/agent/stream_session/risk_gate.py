"""Risk gate for agent stream input.

[INPUT]
- app.services.risk.ingress::screen_user_text (POS: 用户键入文字的风险闸门入口)
- app.schemas.streaming::SSEEnvelope (POS: 业务层 SSE 序列化防腐层)

[OUTPUT]
- check_stream_risk: 对用户输入做风险检测；命中时返回只含规则列表（id、名称、严重度）的 `risk_blocked` SSE 响应，否则返回 None

[POS]
聊天输入进入 agent 流之前的风险闸门。事件不带句子：提示文案由前端按用户语言生成。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi.responses import StreamingResponse

from app.schemas.streaming import SSE_RESPONSE_HEADERS, SSEEnvelope
from app.services.risk.ingress import screen_user_text


async def check_stream_risk(
    text: str,
    chat_id: str | None,
) -> StreamingResponse | None:
    """Run risk detection on user input before processing.

    Returns a StreamingResponse with block-event SSE if blocked, else None. The event names the rules that matched and
    carries no sentence: the client words the notice in the user's language.
    """
    result = await screen_user_text(text, session_id=chat_id)
    if result is None:
        return None

    async def _block_stream() -> AsyncGenerator[str, None]:
        event = {
            "type": "risk_blocked",
            "data": {
                "rules": [
                    {
                        "rule_id": m.rule_id,
                        "display_name": m.display_name,
                        "severity": m.severity,
                    }
                    for m in result.matches
                ],
            },
        }
        yield SSEEnvelope.from_any(event).to_sse_chunk()

    return StreamingResponse(
        content=_block_stream(),
        media_type="text/event-stream",
        headers=SSE_RESPONSE_HEADERS,
    )
