"""Strongly-typed data models for organizational trajectory, value chains, weekly reports, and wiki archiving.

[INPUT]
- Raw events from delegation tasks, generated artifacts, and channel conversation threads.

[OUTPUT]
- ValueChainType: Enum representing the three core enterprise value chains.
- TrajectoryEvent: Structured single execution or decision event.
- WeeklyReportPayload: Aggregated weekly report with evidence references.
- WikiArticleDraft: Formatted markdown draft ready for wiki engine persistence.

[POS]
Domain model definition in app/services/trajectory/.
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field


class ValueChainType(str, enum.Enum):
    """Three core enterprise value chain categories."""

    PRODUCTION = "production"  # Code build, test, sandbox task execution, artifacts
    BUSINESS = "business"      # Feature negotiation, client requirements, delivery milestones
    MANAGEMENT = "management"  # Review approvals, task assignments, risk escalation


@dataclass(frozen=True)
class TrajectoryArtifactRef:
    """Reference to a physical artifact produced during execution."""

    artifact_id: str
    filename: str
    artifact_type: str
    relative_path: str
    byte_size: int = 0
    mime_type: str = "text/plain"


@dataclass(frozen=True)
class TrajectoryEvent:
    """Individual milestone or execution event across the value chain."""

    event_id: str
    chain_type: ValueChainType
    title: str
    summary: str
    timestamp: float = field(default_factory=time.time)
    source_channel: str = "web"
    task_id: str = ""
    session_id: str = ""
    is_key_milestone: bool = False
    artifacts: tuple[TrajectoryArtifactRef, ...] = field(default_factory=tuple)
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class WeeklyReportSection:
    """A single structured section of a weekly report."""

    title: str
    items: list[str] = field(default_factory=list)
    key_metrics: dict[str, str] = field(default_factory=dict)


@dataclass
class WeeklyReportPayload:
    """Complete aggregated weekly report ready for rendering and channel distribution."""

    report_id: str
    start_time: float
    end_time: float
    author_name: str
    completed_highlights: list[str] = field(default_factory=list)
    in_progress_items: list[str] = field(default_factory=list)
    risks_and_blockers: list[str] = field(default_factory=list)
    next_week_plan: list[str] = field(default_factory=list)
    referenced_artifacts: list[TrajectoryArtifactRef] = field(default_factory=list)
    generated_timestamp: float = field(default_factory=time.time)

    def to_markdown(self) -> str:
        """Render the weekly report into standard clean Markdown."""
        lines: list[str] = [
            "# 📊 个人/团队工作周报",
            f"> **报告周期**：`{time.strftime('%Y-%m-%d', time.localtime(self.start_time))}` ~ `{time.strftime('%Y-%m-%d', time.localtime(self.end_time))}`  |  **汇总人**：{self.author_name}",
            "",
            "## 🚀 本周核心交付与成果",
        ]

        if self.completed_highlights:
            for item in self.completed_highlights:
                lines.append(f"- {item}")
        else:
            lines.append("- （本周期暂无已归档的核心交付）")

        lines.extend([
            "",
            "## 🔄 进行中任务与技术进展",
        ])
        if self.in_progress_items:
            for item in self.in_progress_items:
                lines.append(f"- {item}")
        else:
            lines.append("- （所有安排任务均已按期交付）")

        lines.extend([
            "",
            "## ⚠️ 风险、阻塞与协同事项",
        ])
        if self.risks_and_blockers:
            for item in self.risks_and_blockers:
                lines.append(f"- {item}")
        else:
            lines.append("- （当前无阻塞与高危风险）")

        lines.extend([
            "",
            "## 📅 下周重点工作规划",
        ])
        if self.next_week_plan:
            for item in self.next_week_plan:
                lines.append(f"- {item}")
        else:
            lines.append("- （按项目 Roadmap 既定节点推进）")

        if self.referenced_artifacts:
            lines.extend([
                "",
                "## 📦 关联交付资产与代码工件",
            ])
            for art in self.referenced_artifacts:
                lines.append(f"- **{art.filename}** (`{art.artifact_type}`) - `{art.relative_path}` ({art.byte_size} bytes)")

        return "\n".join(lines)


@dataclass(frozen=True)
class WikiArticleDraft:
    """Clean structured knowledge base draft ready for wiki engine persistence."""

    doc_id: str
    title: str
    category: str
    markdown_content: str
    tags: tuple[str, ...] = field(default_factory=tuple)
    source_summary: str = ""
    created_at: float = field(default_factory=time.time)
