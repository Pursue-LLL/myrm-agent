"""Skill Quality Alert Rule Model

Business layer model for configurable alert rules.

[POS]
Business layer configuration for skill quality monitoring and alerting.
Enables flexible per-skill alert thresholds and multi-channel notification.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SkillAlertRule(Base):
    """Skill quality alert rule configuration

    Enables flexible alert configuration per skill:
    - Configurable quality thresholds (different skills, different importance)
    - Multi-channel support (Slack/Discord/Email/HTTP)
    - Enable/disable toggle

    Example:
        ```python
        # Core skill with high threshold
        rule = SkillAlertRule(
            skill_id="pdf-generator",
            quality_threshold=0.8,
            channels=["slack", "email"],
            slack_webhook_url="https://hooks.slack.com/...",
            enabled=True,
        )

        # Regular skill with default threshold
        rule = SkillAlertRule(
            skill_id="web-search",
            quality_threshold=0.5,
            channels=["slack"],
            enabled=True,
        )
        ```
    """

    __tablename__ = "skill_alert_rules"

    skill_id: Mapped[str] = mapped_column(String, primary_key=True)
    quality_threshold: Mapped[float] = mapped_column(Float, default=0.5)
    channels: Mapped[list[str]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    slack_webhook_url: Mapped[str | None] = mapped_column(String, nullable=True)
    discord_webhook_url: Mapped[str | None] = mapped_column(String, nullable=True)
    email_recipients: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    http_webhook_url: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
