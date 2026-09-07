"""Strongly-typed data models for natural language chat entity clustering and timeline cron pipeline.

[INPUT]
- Channel message streams, LLM/Rule extraction entities, Cron schedule specs.

[OUTPUT]
- Strongly-typed Dataclasses for Entity Clusters, Timeline Events, Digest Reports, and NL Blueprints.

[POS]
Data plane domain model for `app/channels/digest/`.
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Sequence


class EntityCategory(str, enum.Enum):
    """Categorization of extracted real-world entities."""

    ORGANIZATION = "organization"  # Company, team, research lab, community
    PRODUCT = "product"            # App, model, framework, open-source tool
    PERSON = "person"              # Key researcher, speaker, author, executive
    TECH_CONCEPT = "tech_concept"  # Architecture pattern, algorithm, standard
    INCIDENT_RISK = "incident_risk"# Outage, vulnerability, blocker, breaking change


@dataclass(frozen=True)
class TimelineFactItem:
    """An atomic verified fact or statement associated with an entity."""

    fact_id: str
    content: str
    timestamp: float
    sender_mask: str = "Member"
    raw_message_id: str = ""
    sentiment: str = "neutral"  # positive / negative / neutral
    importance_score: float = 0.5  # 0.0 to 1.0


@dataclass(frozen=True)
class EntityCluster:
    """Clustered entity node containing organized chronological facts."""

    entity_name: str
    category: EntityCategory
    summary: str
    facts: tuple[TimelineFactItem, ...] = field(default_factory=tuple)
    aliases: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class ChatEntityDigestReport:
    """Complete aggregated timeline digest report for multi-channel distribution."""

    report_id: str
    channel_name: str
    chat_id: str
    window_hours: int
    start_time: float
    end_time: float
    clusters: list[EntityCluster] = field(default_factory=list)
    total_messages_scanned: int = 0
    noise_messages_filtered: int = 0
    generated_timestamp: float = field(default_factory=time.time)
    is_empty_digest: bool = False

    def to_markdown(self) -> str:
        """Render the entity-clustered timeline report to clean Markdown."""
        if self.is_empty_digest or not self.clusters:
            return (
                f"# 📊 群聊情报简报 · {self.channel_name}\n\n"
                f"> 统计窗口：过去 {self.window_hours} 小时（{time.strftime('%Y-%m-%d %H:%M', time.localtime(self.start_time))} ~ "
                f"{time.strftime('%H:%M', time.localtime(self.end_time))}）\n\n"
                f"ℹ️ **本统计周期内未检测到高熵业务或技术实体动态（共扫描 {self.total_messages_scanned} 条消息，已自动过滤闲聊噪声）。**"
            )

        lines: list[str] = [
            f"# 📊 群聊情报简报 · {self.channel_name}",
            f"> 统计窗口：过去 {self.window_hours} 小时 | 扫描 {self.total_messages_scanned} 条消息 | 过滤低熵噪声 {self.noise_messages_filtered} 条",
            "",
        ]

        # Group by entity category
        category_order = [
            (EntityCategory.PRODUCT, "🚀 核心产品与开源工具"),
            (EntityCategory.ORGANIZATION, "🏢 组织机构与生态动态"),
            (EntityCategory.TECH_CONCEPT, "💡 架构决策与技术洞察"),
            (EntityCategory.INCIDENT_RISK, "⚠️ 风险预警与异常处置"),
            (EntityCategory.PERSON, "👤 关键观点与发言人声音"),
        ]

        for cat_enum, cat_title in category_order:
            cat_clusters = [c for c in self.clusters if c.category == cat_enum]
            if not cat_clusters:
                continue

            lines.append(f"## {cat_title}")
            lines.append("")
            for cluster in cat_clusters:
                lines.append(f"### 🔹 {cluster.entity_name}")
                lines.append(f"**摘要**：{cluster.summary}")
                lines.append("")
                lines.append("**时间轴演进（Timeline）**：")
                # Sort facts chronologically
                sorted_facts = sorted(cluster.facts, key=lambda f: f.timestamp)
                for fact in sorted_facts:
                    time_str = time.strftime("%H:%M", time.localtime(fact.timestamp))
                    lines.append(f"- `[{time_str}]` **{fact.sender_mask}**：{fact.content}")
                lines.append("")

        lines.append("---")
        lines.append(f"*由 Myrm 渠道数据智能中枢自动生成 · 生成时间 {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.generated_timestamp))}*")
        return "\n".join(lines)


@dataclass(frozen=True)
class NLDigestCronBlueprint:
    """Compiled blueprint parsed from natural language scheduling instructions."""

    target_chat_name: str
    target_chat_id: str
    cron_expression: str
    window_hours: int = 24
    topic_filter: str = ""
    require_entity_clustering: bool = True
    require_timeline: bool = True
    notify_channel: str = "web"
    notify_recipient: str = "current_user"
    is_valid: bool = True
    error_reason: str = ""
