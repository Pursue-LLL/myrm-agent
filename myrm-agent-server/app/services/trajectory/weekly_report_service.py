"""Weekly Report SOP generation and Chat-to-Knowledge wiki archiving service.

Transforms aggregated multi-source trajectory evidence into structured enterprise weekly reports,
renders interactive rich message cards for IM channels, and extracts high-entropy decisions from
chat streams directly into durable wiki article drafts.

[INPUT]
- TrajectoryAggregator instance, temporal period boundaries, author metadata, chat discussion excerpts.

[OUTPUT]
- WeeklyReportPayload & Markdown text.
- Formatted IM Interactive Cards.
- WikiArticleDraft for knowledge base persistence.

[POS]
Domain service in app/services/trajectory/.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Sequence

from .trajectory_aggregator import TrajectoryAggregator
from .trajectory_models import (
    TrajectoryArtifactRef,
    TrajectoryEvent,
    ValueChainType,
    WeeklyReportPayload,
    WikiArticleDraft,
)

logger = logging.getLogger("myrm.services.trajectory.weekly_report")


class WeeklyReportSOPService:
    """Enterprise Weekly Report SOP and Chat-to-Knowledge archival coordinator."""

    def __init__(self, aggregator: TrajectoryAggregator | None = None) -> None:
        self._aggregator = aggregator or TrajectoryAggregator()

    @property
    def aggregator(self) -> TrajectoryAggregator:
        """Access the underlying multi-source trajectory aggregator."""
        return self._aggregator

    def generate_weekly_report(
        self,
        *,
        start_time: float,
        end_time: float,
        author_name: str = "Myrm User",
    ) -> WeeklyReportPayload:
        """Compile a complete evidence-based weekly report for a designated time window.

        Args:
            start_time: Epoch start timestamp.
            end_time: Epoch end timestamp.
            author_name: Name or handle of the report owner.

        Returns:
            WeeklyReportPayload populated with real milestones, progress, and artifact references.
        """
        events = self._aggregator.aggregate_for_period(start_time=start_time, end_time=end_time)

        completed_highlights: list[str] = []
        in_progress_items: list[str] = []
        risks_and_blockers: list[str] = []
        next_week_plan: list[str] = []
        referenced_artifacts: list[TrajectoryArtifactRef] = []

        for evt in events:
            # Aggregate referenced artifacts
            for art in evt.artifacts:
                if not any(a.artifact_id == art.artifact_id for a in referenced_artifacts):
                    referenced_artifacts.append(art)

            # 1. Production Chain
            if evt.chain_type == ValueChainType.PRODUCTION:
                status = evt.metadata.get("status", "completed")
                if status == "completed":
                    completed_highlights.append(f"【生产交付】{evt.title}：{evt.summary}")
                else:
                    in_progress_items.append(f"【生产构建】{evt.title}（状态：{status}）：{evt.summary}")

            # 2. Business Chain
            elif evt.chain_type == ValueChainType.BUSINESS:
                completed_highlights.append(f"【业务协同】{evt.title}：{evt.summary}")

            # 3. Management Chain
            elif evt.chain_type == ValueChainType.MANAGEMENT:
                completed_highlights.append(f"【管理审批】{evt.title} - {evt.summary}")

        # Default fallback plans if empty
        if not next_week_plan:
            next_week_plan.append("继续按季度/月度 Roadmap 既定目标推进核心特性演进与交付")

        report_id = f"rpt_{int(time.time()*1000)}_{hashlib.sha256(author_name.encode()).hexdigest()[:8]}"

        payload = WeeklyReportPayload(
            report_id=report_id,
            start_time=start_time,
            end_time=end_time,
            author_name=author_name,
            completed_highlights=completed_highlights,
            in_progress_items=in_progress_items,
            risks_and_blockers=risks_and_blockers,
            next_week_plan=next_week_plan,
            referenced_artifacts=referenced_artifacts,
            generated_timestamp=time.time(),
        )

        logger.info("Generated weekly report %s for %s (%d highlights)", report_id, author_name, len(completed_highlights))
        return payload

    def build_report_interactive_card(self, payload: WeeklyReportPayload) -> dict[str, object]:
        """Render an IM-ready structured card payload for Feishu/WeChat/DingTalk."""
        highlight_count = len(payload.completed_highlights)
        artifact_count = len(payload.referenced_artifacts)

        return {
            "card_type": "weekly_report_summary",
            "report_id": payload.report_id,
            "title": f"📊 工作周报 · {payload.author_name}",
            "period": f"{time.strftime('%Y-%m-%d', time.localtime(payload.start_time))} ~ {time.strftime('%Y-%m-%d', time.localtime(payload.end_time))}",
            "stats": {
                "highlights_count": highlight_count,
                "artifacts_count": artifact_count,
            },
            "preview_markdown": payload.to_markdown(),
            "actions": [
                {"action_id": "copy_markdown", "label": "📋 一键复制 Markdown"},
                {"action_id": "export_pdf", "label": "📑 导出 PDF"},
                {"action_id": "archive_wiki", "label": "📚 归档至 Wiki"},
            ],
        }

    def archive_chat_to_wiki(
        self,
        *,
        topic_title: str,
        discussion_content: str,
        category: str = "技术方案与架构决策",
        tags: Sequence[str] = ("IM萃取", "架构决策"),
    ) -> WikiArticleDraft:
        """Extract key decisions from a chat discussion and format into a structured wiki draft.

        Args:
            topic_title: Clean title of the extracted wiki page.
            discussion_content: Sanitized discussion notes and decisions.
            category: Wiki folder or category.
            tags: Classification tags.

        Returns:
            WikiArticleDraft ready to be persisted into wiki toolkit storage.
        """
        doc_id = f"wiki_{int(time.time()*1000)}_{hashlib.sha256(topic_title.encode()).hexdigest()[:8]}"

        md_body = [
            f"# 📚 {topic_title}",
            f"> **分类**：`{category}`  |  **归档时间**：`{time.strftime('%Y-%m-%d %H:%M:%S')}`  |  **标签**：{', '.join(tags)}",
            "",
            "## 📌 背景与决策要点",
            discussion_content.strip(),
            "",
            "---",
            "*本条目由 Myrm Chat-to-Knowledge 引擎从团队即时通讯会话中自动萃取归档。*",
        ]

        draft = WikiArticleDraft(
            doc_id=doc_id,
            title=topic_title,
            category=category,
            markdown_content="\n".join(md_body),
            tags=tuple(tags),
            source_summary=discussion_content[:100],
            created_at=time.time(),
        )

        logger.info("Archived chat discussion to wiki draft: %s (%s)", doc_id, topic_title)
        return draft
