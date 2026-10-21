"""Risk screening of the text a user types before an agent reads it.

[INPUT]
- app.services.risk.detection::get_detection_service (POS: 风险检测引擎单例)
- app.platform_utils::get_session_factory (POS: 数据库会话工厂)

[OUTPUT]
- screen_user_text: 被规则拦下时记录命中位置并返回检测结果，否则返回 None；`record=False` 只检测不记录

[POS]
用户键入的文字进入 agent 之前的风险闸门的唯一入口：Web 发送、中途引导（聊天、子 agent、后台任务）、目标文字编辑、
定时任务提示词、看板标题 / 描述 / 评论、IM 入站、委派与系统命令都经由它，所以「哪段文字被拦、怎么记录」只有一份实现；
调用方只决定被拦之后怎样告知用户（REST 入口见 `refusal.py`）。长文本在工作线程里匹配，事件循环不被占住。
启动时未能载入规则（`init_risk_rules` 重试后放弃）的进程，在第一段文字进来时补载入（`ensure_loaded`），不会一直放行到重启。
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.risk.detection import DetectionResult

logger = logging.getLogger(__name__)


async def screen_user_text(text: str | None, *, session_id: str | None, record: bool = True) -> DetectionResult | None:
    """The detection result when a risk rule holds *text*, else None.

    Pass what the user typed, before anything shortens or rewrites it: a long paste replaced by a stub would hide the
    secret from the rules. The hit is recorded (position only, never the text) before returning; a failure to record
    does not let the text through.

    ``record=False`` is for a caller whose text is screened again, with the hit recorded, on the path that follows it
    (the event-trigger dispatch of an IM message, whose chat turn records it), so one held message leaves one record.
    """
    if not text:
        return None

    from app.services.risk.detection import get_detection_service

    service = get_detection_service()
    await service.ensure_loaded()
    if service.rule_count == 0:
        return None

    result = await service.detect_async(text)
    if not result.blocked:
        return None

    if record:
        try:
            from app.platform_utils import get_session_factory

            async with get_session_factory()() as db:
                await service.record_hits(db, result.matches, trace_id=str(uuid.uuid4()), session_id=session_id)
                await db.commit()
        except Exception:
            logger.warning("Failed to record risk hits; the text is held regardless", exc_info=True)
    return result
