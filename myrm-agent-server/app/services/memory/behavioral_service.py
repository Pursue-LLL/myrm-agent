"""Zero-model-cost deterministic behavioral measurement service.

[INPUT]
app.database.models.channel_message::ChannelMessageModel
app.database.repositories.channel_message_repo::ChannelMessageRepository
myrm_agent_harness.toolkits.memory.strategies.behavioral_measurement::(
    BehavioralMessage, BehavioralStatsOptions, RoutineMeasurement,
    compute_routine_measurement, generate_behavioral_profile_candidates
)

[OUTPUT]
BehavioralMeasurementService: 行为特征统计与画像持久化业务服务

[POS]
Server 业务服务层。协调多渠道入站明细、Harness 确定性统计算子以及 ProfileAttribute 持久化。
实现 User Override 锁权保护与毫秒级零模型成本画像刷新。
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from myrm_agent_harness.toolkits.memory.strategies.behavioral_measurement import (
    BehavioralMessage,
    BehavioralStatsOptions,
    RoutineMeasurement,
    compute_routine_measurement,
    generate_behavioral_profile_candidates,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.channel_message import ChannelMessageModel
from app.database.models.memory import ProfileAttribute
from app.database.repositories.channel_message_repo import ChannelMessageRepository
from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

logger = logging.getLogger(__name__)


class BehavioralMeasurementService:
    """Service managing deterministic behavioral routine aggregation and user profile synchronization."""

    @staticmethod
    def _model_to_dto(model: ChannelMessageModel) -> BehavioralMessage:
        """Convert a ChannelMessageModel into a pure Harness BehavioralMessage DTO."""
        ms = int(model.created_at.timestamp() * 1000) if model.created_at else int(datetime.now(UTC).timestamp() * 1000)
        return BehavioralMessage(
            id=model.id,
            chat_id=model.chat_id,
            channel=model.channel,
            sender_id=model.sender_id,
            sender_name=model.sender_name,
            is_self=bool(model.is_self),
            created_at_ms=ms,
            content=model.content or "",
        )

    @classmethod
    async def measure_and_sync_profile(
        cls,
        session: AsyncSession,
        *,
        offset_minutes: int = 480,
        channel: str | None = None,
        since: datetime | None = None,
        limit: int = 2000,
    ) -> RoutineMeasurement:
        """Execute deterministic behavioral aggregation on recent channel messages and update ProfileAttribute.

        Protects user-curated facts: If an existing ProfileAttribute has source == 'user',
        it will never be overridden by automated deterministic calculations.
        """
        raw_messages = await ChannelMessageRepository.get_messages_for_behavioral_analysis(
            session=session,
            channel=channel,
            since=since,
            limit=limit,
        )

        dtos = [cls._model_to_dto(m) for m in raw_messages]
        options = BehavioralStatsOptions(offset_minutes=offset_minutes)

        measurement = compute_routine_measurement(dtos, options)
        candidates = generate_behavioral_profile_candidates(dtos, options)

        for candidate in candidates:
            if not candidate.profile_key:
                continue

            stmt = select(ProfileAttribute).where(ProfileAttribute.attribute_key == candidate.profile_key)
            res = await session.execute(stmt)
            existing = res.scalar_one_or_none()

            # Rule: User manual configuration has absolute priority
            if existing is not None and existing.source == "user":
                logger.info(
                    "Deterministic measurement preserved user-override attribute: key=%s",
                    candidate.profile_key,
                )
                continue

            value_str = candidate.profile_value or json.dumps(candidate.content, ensure_ascii=False)
            if existing is not None:
                existing.attribute_value = value_str
                existing.confidence = candidate.confidence
                existing.source = "deterministic_stat"
                existing.category = "routine"
            else:
                new_attr = ProfileAttribute(
                    id=str(uuid4()),
                    attribute_key=candidate.profile_key,
                    attribute_value=value_str,
                    category="routine",
                    confidence=candidate.confidence,
                    source="deterministic_stat",
                )
                session.add(new_attr)

        await session.flush()

        try:
            get_event_bus().publish(
                AppEvent(
                    event_type=AppEventType.MEMORY_OPERATION,
                    data={
                        "operation": "behavioral_measurement_synced",
                        "self_message_count": measurement.self_message_count,
                        "latency_sample_count": measurement.latency_sample_count,
                        "peak_active_window": measurement.peak_active_window,
                        "offset_minutes": offset_minutes,
                    },
                )
            )
        except Exception:
            pass

        return measurement

    @classmethod
    async def get_current_insights(
        cls,
        session: AsyncSession,
        *,
        offset_minutes: int = 480,
    ) -> dict[str, Any]:
        """Fetch current behavioral insights, calculating on-demand if no persisted records exist."""
        stmt = select(ProfileAttribute).where(
            ProfileAttribute.category == "routine",
            ProfileAttribute.attribute_key.in_(["routine_active_hours", "routine_reply_latency"]),
        )
        res = await session.execute(stmt)
        attributes = {attr.attribute_key: attr for attr in res.scalars().all()}

        active_data: dict[str, Any] | None = None
        latency_data: dict[str, Any] | None = None

        if "routine_active_hours" in attributes:
            try:
                active_data = json.loads(attributes["routine_active_hours"].attribute_value)
            except Exception:
                pass

        if "routine_reply_latency" in attributes:
            try:
                latency_data = json.loads(attributes["routine_reply_latency"].attribute_value)
            except Exception:
                pass

        # If empty or not yet persisted, compute live metrics
        if not active_data and not latency_data:
            measurement = await cls.measure_and_sync_profile(session, offset_minutes=offset_minutes)
            return {
                "hour_histogram": measurement.hour_histogram,
                "weekday_histogram": measurement.weekday_histogram,
                "reply_latency_p50_ms": measurement.reply_latency_p50_ms,
                "reply_latency_p90_ms": measurement.reply_latency_p90_ms,
                "self_message_count": measurement.self_message_count,
                "latency_sample_count": measurement.latency_sample_count,
                "channel_distribution": measurement.channel_distribution,
                "peak_active_window": measurement.peak_active_window,
                "offset_minutes": offset_minutes,
                "source": "live_computed",
            }

        return {
            "hour_histogram": active_data.get("hour_histogram", [0] * 24) if active_data else [0] * 24,
            "weekday_histogram": active_data.get("weekday_histogram", [0] * 7) if active_data else [0] * 7,
            "reply_latency_p50_ms": latency_data.get("p50_ms") if latency_data else None,
            "reply_latency_p90_ms": latency_data.get("p90_ms") if latency_data else None,
            "self_message_count": active_data.get("sample_count", 0) if active_data else 0,
            "latency_sample_count": latency_data.get("sample_count", 0) if latency_data else 0,
            "channel_distribution": active_data.get("channel_distribution", {}) if active_data else {},
            "peak_active_window": active_data.get("peak_active_window") if active_data else None,
            "offset_minutes": active_data.get("offset_minutes", offset_minutes) if active_data else offset_minutes,
            "source": "persisted",
        }
