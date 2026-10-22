"""Risk gate for agent stream input.

[INPUT]
- app.services.risk.ingress::screen_user_text (POS: 用户键入文字的风险闸门入口)
- app.services.risk.refusal::risk_rules_payload (POS: 拒绝载荷里的规则列表)
- app.schemas.streaming::SSEEnvelope (POS: 业务层 SSE 序列化防腐层)

[OUTPUT]
- check_stream_risk: 对用户输入做风险检测；命中时返回只含规则列表（id、名称、严重度）的 `risk_blocked` SSE 响应，否则返回 None
- resume_typed_texts: 一次 HITL 恢复里用户亲手键入的文字（审批的驳回理由与指引）；选项、改过的工具参数、调整后的计划不在其中

[POS]
聊天输入进入 agent 流之前的风险闸门。事件不带句子：提示文案由前端按用户语言生成。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Mapping

from fastapi.responses import StreamingResponse

from app.schemas.streaming import SSE_RESPONSE_HEADERS, SSEEnvelope
from app.services.risk.ingress import screen_user_text
from app.services.risk.refusal import risk_rules_payload


async def check_stream_risk(
    text: str | None,
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
        event = {"type": "risk_blocked", "data": {"rules": risk_rules_payload(result)}}
        yield SSEEnvelope.from_any(event).to_sse_chunk()

    return StreamingResponse(
        content=_block_stream(),
        media_type="text/event-stream",
        headers=SSE_RESPONSE_HEADERS,
    )


_TYPED_DECISION_FIELDS = ("feedback", "guidance")


def resume_typed_texts(resume_value: Mapping[str, object]) -> list[str]:
    """The texts a user typed into the approval answer a run resumes with: a rejection reason and the guidance that goes
    with a decision.

    Everything else in a resume is picked or edited from what the agent proposed (clarification options, edited tool
    arguments, an adjusted plan). Screening it would hold a click on text the user never wrote, so it is left out.
    """
    entries: list[Mapping[str, object]] = []
    if "decision" in resume_value:
        # A semantic-DOM approval carries its decision and feedback at the top level.
        entries.append(resume_value)
    decisions = resume_value.get("decisions")
    if isinstance(decisions, list):
        entries.extend(entry for entry in decisions if isinstance(entry, dict))
    return [
        text
        for entry in entries
        for field in _TYPED_DECISION_FIELDS
        if isinstance(text := entry.get(field), str) and text.strip()
    ]
