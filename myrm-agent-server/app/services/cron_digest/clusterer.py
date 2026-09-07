"""Entity extraction, fact clustering, and timeline synthesis engine.

[INPUT]
- .models::ClusteredEntityGroup, CompiledCronIntent, EntityFactItem, TimelineDigestPayload
- re, time (standard library)

[OUTPUT]
- EntityTimelineClusterer: Filters noise, clusters raw messages by entities, and constructs chronological timelines.

[POS]
Domain service in app/services/cron_digest/.
"""

from __future__ import annotations

import re
import time
from typing import Sequence

from .models import ClusteredEntityGroup, CompiledCronIntent, EntityFactItem, TimelineDigestPayload


class EntityTimelineClusterer:
    """Extracts entities and builds structured chronological timelines from unstructured message streams."""

    # Entity pattern rules (Company, Product, Technology, Person, Project)
    _ENTITY_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
        ("OpenAI", "company", re.compile(r"\b(?:OpenAI|GPT-4o?|o1|o3-mini|Sora)\b", re.IGNORECASE)),
        ("Anthropic", "company", re.compile(r"\b(?:Anthropic|Claude(?:\s*3\.?5|\s*3\.?7)?(?:\s*Sonnet|\s*Opus)?)\b", re.IGNORECASE)),
        ("DeepSeek", "company", re.compile(r"\b(?:DeepSeek|DeepSeek-R1|DeepSeek-V3)\b", re.IGNORECASE)),
        ("Myrm", "product", re.compile(r"\b(?:Myrm|Myrmidon|Agent-in-Sandbox)\b", re.IGNORECASE)),
        ("Google", "company", re.compile(r"\b(?:Google|Gemini(?:\s*1\.?5|\s*2\.?0)?|DeepMind)\b", re.IGNORECASE)),
        ("ByteDance", "company", re.compile(r"\b(?:豆包|豆包工作|ByteDance|字节跳动)\b", re.IGNORECASE)),
        ("Tencent", "company", re.compile(r"\b(?:腾讯|WorkBuddy|微信|企业微信)\b", re.IGNORECASE)),
        ("Alibaba", "company", re.compile(r"\b(?:阿里|千问|通义千问|钉钉)\b", re.IGNORECASE)),
    )

    # High-frequency noise and chatter filter
    _CHATTER_NOISE_RE = re.compile(
        r"^(?:收到|好的|ok|打卡|哈哈|赞|666|\+1|mark|谢谢|早|晚安|测试|滴|👍|表情)\s*$",
        re.IGNORECASE,
    )

    @classmethod
    def filter_noise(cls, text: str) -> bool:
        """Return True if message contains meaningful factual information (not trivial chatter)."""
        stripped = text.strip()
        if len(stripped) < 4:
            return False
        if cls._CHATTER_NOISE_RE.match(stripped):
            return False
        return True

    @classmethod
    def extract_entities_from_text(cls, text: str) -> list[tuple[str, str]]:
        """Identify known entities and their categories from text."""
        matched: list[tuple[str, str]] = []
        for name, cat, pattern in cls._ENTITY_PATTERNS:
            if pattern.search(text):
                matched.append((name, cat))
        return matched

    @classmethod
    def cluster_messages_to_timeline(
        cls,
        *,
        intent: CompiledCronIntent,
        raw_messages: Sequence[tuple[float, str, str | None]],  # (timestamp, text, message_id)
    ) -> TimelineDigestPayload:
        """Group raw messages into chronological fact timelines centered around core entities."""
        valid_messages: list[tuple[float, str, str | None]] = [
            (ts, text, mid) for ts, text, mid in raw_messages if cls.filter_noise(text)
        ]

        # Sort messages by timestamp ascending
        valid_messages.sort(key=lambda x: x[0])

        entity_buckets: dict[str, tuple[str, list[EntityFactItem]]] = {}
        general_facts: list[EntityFactItem] = []

        for idx, (ts, text, mid) in enumerate(valid_messages):
            time_display = time.strftime("%H:%M", time.localtime(ts))
            fact_id = f"fact_{idx+1}_{int(ts)}"

            entities = cls.extract_entities_from_text(text)
            if entities:
                for ent_name, ent_type in entities:
                    if ent_name not in entity_buckets:
                        entity_buckets[ent_name] = (ent_type, [])
                    entity_buckets[ent_name][1].append(
                        EntityFactItem(
                            fact_id=fact_id,
                            timestamp=ts,
                            time_display=time_display,
                            fact_text=text.strip(),
                            source_message_id=mid,
                        )
                    )
            else:
                # General topic facts
                general_facts.append(
                    EntityFactItem(
                        fact_id=fact_id,
                        timestamp=ts,
                        time_display=time_display,
                        fact_text=text.strip(),
                        source_message_id=mid,
                    )
                )

        groups: list[ClusteredEntityGroup] = []
        for ent_name, (ent_type, facts) in entity_buckets.items():
            summary = f"涵盖 {len(facts)} 条关于 {ent_name} 的动态进展。"
            groups.append(
                ClusteredEntityGroup(
                    entity_name=ent_name,
                    entity_type=ent_type,
                    summary=summary,
                    facts=tuple(facts),
                    importance_score=float(len(facts)),
                )
            )

        if general_facts:
            groups.append(
                ClusteredEntityGroup(
                    entity_name=f"{intent.focus_topic} (综合)",
                    entity_type="topic",
                    summary=f"包含 {len(general_facts)} 条行业研讨与通用讨论。",
                    facts=tuple(general_facts),
                    importance_score=0.5,
                )
            )

        # Sort groups by importance score descending
        groups.sort(key=lambda g: g.importance_score, reverse=True)

        now = time.time()
        start_ts = now - (intent.time_window_hours * 3600)
        tw_display = f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(start_ts))} ~ {time.strftime('%H:%M', time.localtime(now))}"

        digest_id = f"digest_{int(now*1000)}"
        return TimelineDigestPayload(
            digest_id=digest_id,
            title=intent.report_title,
            channel_or_group=intent.target_channel_or_group,
            time_window_display=tw_display,
            generated_at=now,
            entity_groups=tuple(groups),
        )
