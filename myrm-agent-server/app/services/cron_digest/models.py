"""Natural language to Cron task compiler and entity-clustered timeline report models.

[INPUT]
- dataclasses, enum, re, time, typing (standard library)

[OUTPUT]
- CompiledCronIntent: Structured intent extracted from natural language prompt.
- EntityFactItem: Extracted factual point anchored to an entity.
- ClusteredEntityGroup: Group of facts associated with a core entity, arranged on a timeline.
- TimelineDigestPayload: Structured multi-entity timeline briefing ready for channel dispatch.

[POS]
Domain models in app/services/cron_digest/.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Sequence


class DigestScheduleFrequency(str, enum.Enum):
    """Normalized cron scheduling frequencies."""
    DAILY = "daily"
    HOURLY = "hourly"
    WEEKLY = "weekly"
    CUSTOM_CRON = "custom_cron"


@dataclass(frozen=True)
class CompiledCronIntent:
    """Structured cron task compilation result from natural language."""
    cron_expr: str
    target_channel_or_group: str
    time_window_hours: int
    frequency: DigestScheduleFrequency
    report_title: str
    focus_topic: str
    is_valid: bool = True
    error_message: str | None = None


@dataclass(frozen=True)
class EntityFactItem:
    """A factual statement or event anchored with a timestamp."""
    fact_id: str
    timestamp: float
    time_display: str
    fact_text: str
    source_message_id: str | None = None
    sentiment: str = "neutral"  # positive, neutral, negative, risk


@dataclass(frozen=True)
class ClusteredEntityGroup:
    """An entity (company, project, product, person) with associated timeline events."""
    entity_name: str
    entity_type: str  # company, product, technology, person, event
    summary: str
    facts: tuple[EntityFactItem, ...] = field(default_factory=tuple)
    importance_score: float = 1.0


@dataclass(frozen=True)
class TimelineDigestPayload:
    """Complete entity-clustered timeline report ready for rendering and delivery."""
    digest_id: str
    title: str
    channel_or_group: str
    time_window_display: str
    generated_at: float
    entity_groups: tuple[ClusteredEntityGroup, ...] = field(default_factory=tuple)

    def to_markdown(self) -> str:
        """Render markdown representation of the entity timeline digest."""
        lines: list[str] = [
            f"# ⏱️ {self.title}",
            f"> **信源**：`{self.channel_or_group}`  |  **时间跨度**：`{self.time_window_display}`",
            "",
        ]

        if not self.entity_groups:
            lines.append("*在选定时间窗口内未检测到高信息量实体动态。*")
            return "\n".join(lines)

        for group in self.entity_groups:
            type_icon = {
                "company": "🏢",
                "product": "📦",
                "technology": "⚡",
                "person": "👤",
                "event": "🎯",
            }.get(group.entity_type, "📌")

            lines.append(f"### {type_icon} 【{group.entity_type.upper()}】{group.entity_name}")
            lines.append(f"**核心要点**：{group.summary}")
            lines.append("")
            lines.append("**事件时间轴**：")
            for fact in group.facts:
                lines.append(f"- `[{fact.time_display}]` {fact.fact_text}")
            lines.append("")

        lines.append("---")
        lines.append("*由 Myrm Entity-Timeline Engine 自动聚类萃取生成*")
        return "\n".join(lines)
