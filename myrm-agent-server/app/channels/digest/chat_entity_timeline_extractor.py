"""Chat entity extraction, fact clustering, and chronological timeline generation engine.

[INPUT]
- Raw multi-channel chat message list, time window configuration.

[OUTPUT]
- Structured ChatEntityDigestReport with EntityClusters and TimelineFactItems.

[POS]
Extraction and clustering logic for `app/channels/digest/`.
"""

from __future__ import annotations

import hashlib
import re
import time
from typing import Sequence

from app.channels.digest.entity_timeline_models import (
    ChatEntityDigestReport,
    EntityCategory,
    EntityCluster,
    TimelineFactItem,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Known technical entities and keywords for deterministic high-precision matching
DEFAULT_KNOWN_ENTITIES: dict[str, tuple[EntityCategory, tuple[str, ...]]] = {
    "DeepSeek": (EntityCategory.PRODUCT, ("deepseek-v3", "deepseek-r1", "deepseek")),
    "Claude": (EntityCategory.PRODUCT, ("claude-3.5-sonnet", "claude-3.7-sonnet", "claude")),
    "OpenAI": (EntityCategory.ORGANIZATION, ("openai", "gpt-4o", "chatgpt")),
    "Myrm": (EntityCategory.PRODUCT, ("myrm", "myrm-agent", "myrm-harness")),
    "Hermes": (EntityCategory.PRODUCT, ("hermes", "hermes-agent")),
    "OpenClaw": (EntityCategory.PRODUCT, ("openclaw", "claw")),
    "WorkBuddy": (EntityCategory.PRODUCT, ("workbuddy",)),
    "豆包工作": (EntityCategory.PRODUCT, ("doubao", "豆包")),
    "千问办公": (EntityCategory.PRODUCT, ("tongyi", "千问")),
    "Postgres": (EntityCategory.TECH_CONCEPT, ("postgresql", "postgres", "pg")),
    "Qdrant": (EntityCategory.TECH_CONCEPT, ("qdrant", "向量库")),
    "Docker/沙箱": (EntityCategory.TECH_CONCEPT, ("docker", "container", "sandbox", "沙箱")),
    "线上故障/告警": (EntityCategory.INCIDENT_RISK, ("bug", "error", "panic", "crash", "500", "故障", "告警", "中断")),
}

# Heuristic noise patterns (emojis, very short greetings, pure system commands)
NOISE_PATTERNS = [
    re.compile(r"^/([a-zA-Z0-9_-]+)"),  # Slash commands
    re.compile(r"^(收到|好的|ok|OK|1|666|赞|👍|🐮|哈+|嗯+|测试|test)$", re.IGNORECASE),
]


class ChatEntityTimelineExtractor:
    """Extracts entities, deduplicates facts, and compiles timeline digests."""

    def __init__(self, known_entities: dict[str, tuple[EntityCategory, tuple[str, ...]]] | None = None) -> None:
        self._known_entities = known_entities or DEFAULT_KNOWN_ENTITIES

    def is_noise_message(self, text: str) -> bool:
        """Heuristically filter out low-entropy chatting noise."""
        stripped = text.strip()
        if len(stripped) < 4:
            return True
        for pattern in NOISE_PATTERNS:
            if pattern.match(stripped):
                return True
        return False

    def extract_entity_occurrences(self, text: str) -> list[tuple[str, EntityCategory]]:
        """Identify which known entities are mentioned in the message text."""
        lowered = text.lower()
        matched: list[tuple[str, EntityCategory]] = []
        for canonical_name, (category, aliases) in self._known_entities.items():
            if canonical_name.lower() in lowered:
                matched.append((canonical_name, category))
                continue
            for alias in aliases:
                if alias in lowered:
                    matched.append((canonical_name, category))
                    break
        return matched

    def build_digest(
        self,
        *,
        channel_name: str,
        chat_id: str,
        messages: Sequence[dict[str, object]],
        window_hours: int = 24,
        topic_filter: str = "",
    ) -> ChatEntityDigestReport:
        """Process messages into an entity-clustered timeline report.

        Each item in `messages` must contain:
        - 'text': str
        - 'timestamp': float (seconds)
        - 'sender_name': str (optional, defaults to 'Member')
        - 'message_id': str (optional)
        """
        now = time.time()
        start_time = now - (window_hours * 3600)
        report_id = f"dig_{int(now*1000)}_{hashlib.sha256(f'{channel_name}:{chat_id}'.encode()).hexdigest()[:8]}"

        total_scanned = len(messages)
        noise_filtered = 0
        valid_items: list[tuple[str, EntityCategory, TimelineFactItem]] = []

        topic_kw = topic_filter.strip().lower()

        for msg in messages:
            raw_text = str(msg.get("text", "")).strip()
            msg_ts = float(msg.get("timestamp", now))
            sender = str(msg.get("sender_name", "Member"))
            msg_id = str(msg.get("message_id", ""))

            # Time window check
            if msg_ts < start_time:
                continue

            # Topic filter
            if topic_kw and topic_kw not in raw_text.lower():
                continue

            # Noise filter
            if self.is_noise_message(raw_text):
                noise_filtered += 1
                continue

            # Entity matching
            detected_entities = self.extract_entity_occurrences(raw_text)
            if not detected_entities:
                # If no specific known entity matches, group under generic topic category
                generic_name = "综合动态与讨论"
                fact_id = f"f_{hashlib.md5(f'{msg_ts}:{raw_text}'.encode()).hexdigest()[:8]}"
                valid_items.append((
                    generic_name,
                    EntityCategory.TECH_CONCEPT,
                    TimelineFactItem(
                        fact_id=fact_id,
                        content=raw_text,
                        timestamp=msg_ts,
                        sender_mask=sender,
                        raw_message_id=msg_id,
                    ),
                ))
            else:
                for ent_name, ent_cat in detected_entities:
                    fact_id = f"f_{hashlib.md5(f'{msg_ts}:{ent_name}:{raw_text}'.encode()).hexdigest()[:8]}"
                    valid_items.append((
                        ent_name,
                        ent_cat,
                        TimelineFactItem(
                            fact_id=fact_id,
                            content=raw_text,
                            timestamp=msg_ts,
                            sender_mask=sender,
                            raw_message_id=msg_id,
                        ),
                    ))

        # Group facts by entity
        cluster_dict: dict[str, tuple[EntityCategory, list[TimelineFactItem]]] = {}
        for ent_name, ent_cat, fact_item in valid_items:
            if ent_name not in cluster_dict:
                cluster_dict[ent_name] = (ent_cat, [])
            cluster_dict[ent_name][1].append(fact_item)

        clusters: list[EntityCluster] = []
        for ent_name, (ent_cat, facts) in cluster_dict.items():
            # Generate summary based on facts count and time span
            summary = f"共涉及 {len(facts)} 条关键记录，涵盖讨论、更新与反馈动态。"
            clusters.append(EntityCluster(
                entity_name=ent_name,
                category=ent_cat,
                summary=summary,
                facts=tuple(facts),
            ))

        is_empty = len(clusters) == 0

        return ChatEntityDigestReport(
            report_id=report_id,
            channel_name=channel_name,
            chat_id=chat_id,
            window_hours=window_hours,
            start_time=start_time,
            end_time=now,
            clusters=clusters,
            total_messages_scanned=total_scanned,
            noise_messages_filtered=noise_filtered,
            generated_timestamp=now,
            is_empty_digest=is_empty,
        )
