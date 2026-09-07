"""Weekly/Daily report standard operating procedure (SOP) and Chat-to-Knowledge archiver.

Transforms aggregated multi-source trajectory evidence into executive-ready
weekly/daily summaries with verifiable sandbox artifacts and writes technical
decisions directly into the enterprise Wiki knowledge base.

[INPUT]
- .trajectory_aggregator::AggregatedTrajectory, WorkTrajectoryItem, GroupDecisionItem
- myrm_agent_harness.toolkits.wiki::WikiStructure, WikiPendingEditsManager, WikiProvenance
- typing and standard library formatting

[OUTPUT]
- WeeklyReportPayload: Formatted weekly report container (Markdown + summary stats).
- WikiArchiveResult: Result envelope for Chat-to-Knowledge extraction.
- WeeklyReportSOPService: Core orchestration service.

[POS]
Weekly reporting SOP and Chat-to-Knowledge domain engine for app/channels/delegation/.
"""

from __future__ import annotations

import datetime
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from .trajectory_aggregator import AggregatedTrajectory, GroupDecisionItem, WorkTrajectoryItem

logger = logging.getLogger("myrm.channels.delegation.weekly_report_sop")


@dataclass(frozen=True)
class WeeklyReportPayload:
    """Formatted weekly/daily report ready for IM card delivery and user copying."""

    title: str
    markdown_content: str
    summary_overview: str
    total_tasks_completed: int
    total_artifacts_produced: int
    completion_rate_percent: int
    generated_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class WikiArchiveResult:
    """Result of archiving chat discussions/decisions into the Wiki knowledge base."""

    concept_name: str
    file_path: str
    archived_chars: int
    success: bool
    error_message: str = ""


class WeeklyReportSOPService:
    """Standard operating procedure engine for weekly report generation and knowledge archiving."""

    def __init__(self, wiki_root_dir: Path | str | None = None) -> None:
        self._wiki_root_dir = Path(wiki_root_dir) if wiki_root_dir else None

    def render_weekly_report(
        self,
        trajectory: AggregatedTrajectory,
        *,
        report_title: str = "",
        user_display_name: str = "Developer",
    ) -> WeeklyReportPayload:
        """Render a verifiable, executive-ready weekly report in clean Markdown.

        Args:
            trajectory: Aggregated activity and artifact evidence.
            report_title: Optional custom report title.
            user_display_name: Formatted user name for header.

        Returns:
            WeeklyReportPayload with Markdown and structured statistics.
        """
        start_date = datetime.date.fromtimestamp(trajectory.start_time).strftime("%Y-%m-%d") if trajectory.start_time > 0 else "Beginning"
        end_date = datetime.date.fromtimestamp(trajectory.end_time).strftime("%Y-%m-%d")
        
        effective_title = report_title or f"📊 工作周报 ({start_date} ~ {end_date})"
        completion_pct = int(trajectory.completion_rate * 100)

        lines: list[str] = [
            f"# {effective_title}",
            f"> 责任人: **{user_display_name}** | 任务完成率: **{completion_pct}%** ({len(trajectory.completed_items)}/{trajectory.total_tasks_count}) | 产出工件: **{len(trajectory.artifacts)}** 个",
            "",
            "## 一、 本周重点产出与成果（真实证据链）",
        ]

        if trajectory.completed_items:
            for idx, item in enumerate(trajectory.completed_items, 1):
                cat_tag = f"[{item.category.value.upper()}]"
                lines.append(f"### {idx}. {cat_tag} {item.title}")
                lines.append(f"- **执行摘要**: {item.summary}")
                if item.duration_seconds > 0:
                    lines.append(f"- **耗时**: {int(item.duration_seconds)} 秒")
                if item.artifacts:
                    art_desc = ", ".join(f"`{a.file_name}` ({max(1, a.file_size_bytes // 1024)} KB)" for a in item.artifacts)
                    lines.append(f"- **交付工件**: {art_desc}")
                lines.append("")
        else:
            lines.append("- *本周期暂无已归档的沙箱完成任务。*")
            lines.append("")

        lines.append("## 二、 重点技术决策与协同记录")
        if trajectory.decisions:
            for idx, d in enumerate(trajectory.decisions, 1):
                lines.append(f"{idx}. **{d.topic}** (负责人: `{d.decision_maker}`)")
                lines.append(f"   - 决策结论: {d.summary}")
                if d.tags:
                    lines.append(f"   - 标签: `{'`, `'.join(d.tags)}`")
            lines.append("")
        else:
            lines.append("- *本周期未登记关键群聊/会议决策。*")
            lines.append("")

        lines.append("## 三、 进行中及未竟事项")
        if trajectory.in_progress_items:
            for item in trajectory.in_progress_items:
                lines.append(f"- ⏳ **{item.title}** (当前状态: `{item.status.value}`)")
        else:
            lines.append("- *无阻塞中或进行中的遗留任务。*")
        lines.append("")

        if trajectory.failed_items:
            lines.append("## 四、 风险预警与异常复盘")
            for item in trajectory.failed_items:
                lines.append(f"- ⚠️ **{item.title}**: {item.summary}")
            lines.append("")

        lines.append("## 五、 下周核心目标规划")
        lines.append("1. 推进现有在研任务闭环与自动化验证；")
        lines.append("2. 持续强化系统稳定性与多渠道协同能力；")
        lines.append("3. 沉淀核心技术资产至团队 Wiki 知识库。")

        markdown_body = "\n".join(lines)
        overview = f"完成 {len(trajectory.completed_items)} 个重点任务，产出 {len(trajectory.artifacts)} 个交付物，完成率 {completion_pct}%。"

        return WeeklyReportPayload(
            title=effective_title,
            markdown_content=markdown_body,
            summary_overview=overview,
            total_tasks_completed=len(trajectory.completed_items),
            total_artifacts_produced=len(trajectory.artifacts),
            completion_rate_percent=completion_pct,
        )

    def archive_chat_decision_to_wiki(
        self,
        decision: GroupDecisionItem,
        *,
        subfolder: str = "decisions",
    ) -> WikiArchiveResult:
        """Archive a technical or product decision into a structured markdown Wiki document.

        Args:
            decision: Extracted chat decision record.
            subfolder: Relative subfolder inside Wiki structure.

        Returns:
            WikiArchiveResult indicating path and status.
        """
        if not self._wiki_root_dir:
            return WikiArchiveResult(
                concept_name=decision.topic,
                file_path="",
                archived_chars=0,
                success=False,
                error_message="Wiki root directory not configured.",
            )

        try:
            target_dir = self._wiki_root_dir / subfolder
            target_dir.mkdir(parents=True, exist_ok=True)

            safe_topic = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in decision.topic).strip("_")
            if not safe_topic:
                safe_topic = f"decision_{decision.decision_id}"

            file_path = target_dir / f"{safe_topic}.md"

            content_lines = [
                "---",
                f"title: \"{decision.topic}\"",
                f"decision_id: \"{decision.decision_id}\"",
                f"decision_maker: \"{decision.decision_maker}\"",
                f"channel_id: \"{decision.channel_id}\"",
                f"tags: [{', '.join(f'\"{t}\"' for t in decision.tags)}]",
                f"archived_at: \"{datetime.datetime.fromtimestamp(decision.timestamp).isoformat()}\"",
                "---",
                "",
                f"# 决策记录: {decision.topic}",
                "",
                "## 1. 决策背景与结论",
                decision.summary,
                "",
                "## 2. 关联任务与执行人",
                f"- **决策者**: {decision.decision_maker}",
                f"- **讨论来源渠道**: {decision.channel_id}",
            ]

            if decision.related_task_ids:
                content_lines.append(f"- **关联沙箱任务 ID**: `{', '.join(decision.related_task_ids)}`")

            doc_body = "\n".join(content_lines)
            file_path.write_text(doc_body, encoding="utf-8")

            logger.info("WeeklyReportSOPService: Successfully archived decision to %s", file_path)
            return WikiArchiveResult(
                concept_name=decision.topic,
                file_path=str(file_path),
                archived_chars=len(doc_body),
                success=True,
            )
        except Exception as exc:
            logger.error("WeeklyReportSOPService: Failed to archive decision %s: %s", decision.decision_id, exc)
            return WikiArchiveResult(
                concept_name=decision.topic,
                file_path="",
                archived_chars=0,
                success=False,
                error_message=str(exc),
            )
