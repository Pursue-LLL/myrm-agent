"""Natural Language to Entity-Clustered Timeline Cron Pipeline Compiler and Coordinator.

[INPUT]
- Natural language prompts from users (e.g. '总结一下群聊好记星最近24小时的AI消息，之后定时早上九点发我一个报告，按照新闻的实体做消息聚类和时间轴').
- Channel message repositories, Cron scheduler adapters.

[OUTPUT]
- Standard NLDigestCronBlueprint and CronJob configurations for autonomous background execution.

[POS]
Pipeline coordinator for `app/channels/digest/`.
"""

from __future__ import annotations

import re
from typing import Sequence

from app.channels.digest.chat_entity_timeline_extractor import ChatEntityTimelineExtractor
from app.channels.digest.entity_timeline_models import (
    ChatEntityDigestReport,
    NLDigestCronBlueprint,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


class NLDigestCronPipeline:
    """Compiles natural language scheduling requests into automated digest cron workflows."""

    def __init__(self, extractor: ChatEntityTimelineExtractor | None = None) -> None:
        self._extractor = extractor or ChatEntityTimelineExtractor()

    def parse_blueprint_from_prompt(
        self,
        prompt: str,
        *,
        default_chat_id: str = "current_group",
        known_chat_names: dict[str, str] | None = None,
    ) -> NLDigestCronBlueprint:
        """Parse natural language instruction into structured cron blueprint."""
        text = prompt.strip()
        chat_map = known_chat_names or {}

        # 1. Target chat extraction
        target_chat_name = "当前群聊"
        target_chat_id = default_chat_id

        chat_match = re.search(r"(?:群聊|群组|频道|在|从)\s*([a-zA-Z0-9_\u4e00-\u9fa5]+)", text)
        if chat_match:
            cand_name = chat_match.group(1).strip()
            if cand_name in chat_map:
                target_chat_name = cand_name
                target_chat_id = chat_map[cand_name]
            elif cand_name not in ("最近", "每天", "定时", "今天"):
                target_chat_name = cand_name
                target_chat_id = f"chat_{cand_name}"

        # 2. Window hours extraction (e.g. 24小时, 48h, 7天)
        window_hours = 24
        window_match = re.search(r"(\d+)\s*(?:小时|个?小时|h|hr|hours)", text, re.IGNORECASE)
        if window_match:
            window_hours = int(window_match.group(1))
        else:
            day_match = re.search(r"(\d+)\s*(?:天|days?)", text, re.IGNORECASE)
            if day_match:
                window_hours = int(day_match.group(1)) * 24

        # 3. Time schedule extraction (e.g. 早上9点 -> 0 9 * * *, 下午5点半 -> 30 17 * * *)
        cron_expr = "0 9 * * *"  # Default: daily 09:00

        time_match = re.search(r"(?:早上|上午|早晨)?\s*(\d{1,2})(?:点|时)(?:(\d{1,2})分)?", text)
        afternoon_match = re.search(r"(?:下午|晚上|傍晚)\s*(\d{1,2})(?:点|时)(?:(\d{1,2})分)?", text)

        if afternoon_match:
            hour = int(afternoon_match.group(1))
            if hour < 12:
                hour += 12
            minute = int(afternoon_match.group(2)) if afternoon_match.group(2) else 0
            cron_expr = f"{minute} {hour} * * *"
        elif time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2)) if time_match.group(2) else 0
            cron_expr = f"{minute} {hour} * * *"

        # 4. Topic extraction
        topic_filter = ""
        topic_match = re.search(r"(?:关于|对于|相关|的)\s*([a-zA-Z0-9_\u4e00-\u9fa5]+)\s*(?:消息|动态|资讯|新闻|讨论)", text)
        if topic_match:
            cand_topic = topic_match.group(1).strip()
            if cand_topic not in ("最近", "重要", "全部", "所有"):
                topic_filter = cand_topic

        # 5. Entity clustering and timeline flags
        require_clustering = "实体" in text or "聚类" in text or "归类" in text or True
        require_timeline = "时间轴" in text or "时间线" in text or "按时间" in text or True

        return NLDigestCronBlueprint(
            target_chat_name=target_chat_name,
            target_chat_id=target_chat_id,
            cron_expression=cron_expr,
            window_hours=window_hours,
            topic_filter=topic_filter,
            require_entity_clustering=require_clustering,
            require_timeline=require_timeline,
            notify_channel="web",
            notify_recipient="current_user",
            is_valid=True,
        )

    def execute_digest_workflow(
        self,
        blueprint: NLDigestCronBlueprint,
        messages: Sequence[dict[str, object]],
    ) -> ChatEntityDigestReport:
        """Execute the digest extraction on the target message stream."""
        logger.info(
            "Executing digest workflow for chat=%s (id=%s, window=%dh, topic='%s')",
            blueprint.target_chat_name,
            blueprint.target_chat_id,
            blueprint.window_hours,
            blueprint.topic_filter,
        )
        return self._extractor.build_digest(
            channel_name=blueprint.target_chat_name,
            chat_id=blueprint.target_chat_id,
            messages=messages,
            window_hours=blueprint.window_hours,
            topic_filter=blueprint.topic_filter,
        )
