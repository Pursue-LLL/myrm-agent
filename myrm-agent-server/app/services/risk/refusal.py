"""How a text that a risk rule holds is refused to an HTTP client.

[INPUT]
- app.services.risk.ingress::screen_user_text (POS: 用户键入文字的风险闸门入口)

[OUTPUT]
- RISK_HELD_CODE: the code the client recognises a refusal by
- risk_rules_payload: the rules that held a text, which the client words the notice from
- reject_if_risky: raises the refusal when a rule holds any of the texts

[POS]
REST 入口与聊天 SSE 事件共用的拒绝载荷：只含规则的 id、名称、严重度，不含任何句子，也不含被拦的原文；提示文案由前端按用户语言生成。
REST 入口被拦时返回 400，`detail` 为 `{"code": "risk_held", "message", "rules"}`，前端的统一请求层据 `code` 弹出同一条本地化提示。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException

from app.services.risk.ingress import screen_user_text

if TYPE_CHECKING:
    from app.services.risk.detection import DetectionResult

RISK_HELD_CODE = "risk_held"


def risk_rules_payload(result: DetectionResult) -> list[dict[str, str]]:
    """The rules that held a text: id, name and severity of each."""
    return [{"rule_id": m.rule_id, "display_name": m.display_name, "severity": m.severity} for m in result.matches]


async def reject_if_risky(*texts: str | None, session_id: str | None = None) -> None:
    """Raise the 400 refusal when a risk rule holds one of *texts*; each is screened on its own.

    Texts are screened separately because two fields of one request are not one sentence: a rule that reads
    ``key = value`` must not pair a word from one field with a token from another.
    """
    for text in texts:
        result = await screen_user_text(text, session_id=session_id)
        if result is not None:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": RISK_HELD_CODE,
                    "message": "Text held by a risk rule",
                    "rules": risk_rules_payload(result),
                },
            )
