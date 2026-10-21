"""Weekly Report SOP and Chat-to-Knowledge archival adapter for delegation channel.

[INPUT]
- .delegation_models::DeliveryArtifact
- .trajectory_aggregator::AggregatedTrajectory, GroupDecisionItem, WorkTrajectoryItem
- pathlib::Path

[OUTPUT]
- WeeklyReportPayload: Rendered markdown payload for IM/email delivery.
- WikiArchiveResult: Result of archiving decisions to wiki directory.
- WeeklyReportSOPService: SOP service for generating weekly reports and wiki pages.

[POS]
Adapter service connecting delegation trajectories to executive-ready weekly reports
and wiki knowledge bases in app/channels/delegation/.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from .trajectory_aggregator import AggregatedTrajectory, GroupDecisionItem

logger = logging.getLogger("myrm.channels.delegation.weekly_report_sop")


@dataclass(frozen=True)
class WeeklyReportPayload:
    """Rendered weekly report artifact ready for channel distribution."""

    total_tasks_completed: int
    total_artifacts_produced: int
    completion_rate_percent: int
    markdown_content: str


@dataclass(frozen=True)
class WikiArchiveResult:
    """Result of archiving a group chat decision into the wiki knowledge base."""

    success: bool
    file_path: str
    decision_id: str


class WeeklyReportSOPService:
    """Generates executive markdown weekly reports and archives group decisions to wiki."""

    def __init__(self, wiki_root_dir: Path | str | None = None) -> None:
        self.wiki_root_dir = Path(wiki_root_dir) if wiki_root_dir else Path("/tmp/myrm_wiki")

    def render_weekly_report(
        self,
        trajectory: AggregatedTrajectory,
        *,
        user_display_name: str = "团队成员",
    ) -> WeeklyReportPayload:
        """Render a formatted markdown weekly report from aggregated trajectory data."""
        completed_count = len(trajectory.completed_items)
        artifacts_count = len(trajectory.artifacts)
        rate_pct = int(trajectory.completion_rate * 100)

        lines: list[str] = [
            f"# 📊 工作周报 · {user_display_name}",
            f"> 统计周期：{time.strftime('%Y-%m-%d', time.localtime(trajectory.start_time))} ~ {time.strftime('%Y-%m-%d', time.localtime(trajectory.end_time))}",
            f"> 任务完成率：`{rate_pct}%`（已完成 {completed_count}/{trajectory.total_tasks_count}）",
            "",
            "## 🎯 本周核心交付",
        ]

        if not trajectory.completed_items:
            lines.append("- （无已完成任务）")
        else:
            for item in trajectory.completed_items:
                lines.append(f"- **{item.title}**：{item.summary}")

        lines.extend(["", "## 📦 产出工件清单"])
        if not trajectory.artifacts:
            lines.append("- （无产出工件）")
        else:
            for art in trajectory.artifacts:
                lines.append(f"- `{art.file_name}` ({art.file_size_bytes} 字节)")

        if trajectory.decisions:
            lines.extend(["", "## 💡 关键技术决策"])
            for d in trajectory.decisions:
                lines.append(f"- **{d.topic}** ({d.decision_maker})：{d.summary}")

        content = "\n".join(lines)

        return WeeklyReportPayload(
            total_tasks_completed=completed_count,
            total_artifacts_produced=artifacts_count,
            completion_rate_percent=rate_pct,
            markdown_content=content,
        )

    def archive_chat_decision_to_wiki(
        self,
        decision: GroupDecisionItem,
        *,
        subfolder: str = "decisions",
    ) -> WikiArchiveResult:
        """Archive a group chat decision item into local markdown wiki files."""
        target_dir = self.wiki_root_dir / subfolder
        target_dir.mkdir(parents=True, exist_ok=True)

        filename = f"decision_{decision.decision_id}.md"
        file_path = target_dir / filename

        md_content = [
            f"# {decision.topic}",
            f"- **决策人**：{decision.decision_maker}",
            f"- **来源群聊**：{decision.channel_id}",
            f"- **时间**：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(decision.timestamp))}",
            f"- **标签**：{', '.join(decision.tags) if decision.tags else '无'}",
            "",
            "## 决策摘要",
            decision.summary,
        ]

        file_path.write_text("\n".join(md_content), encoding="utf-8")
        logger.info("Archived chat decision to wiki: %s", file_path)

        return WikiArchiveResult(
            success=True,
            file_path=str(file_path),
            decision_id=decision.decision_id,
        )
