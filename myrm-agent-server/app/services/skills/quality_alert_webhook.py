"""Skill Quality Alert Webhook

Business layer webhook for proactive skill quality monitoring.
Sends alerts when skill quality drops below configurable thresholds.

[INPUT]
- app.models.skill_alert_rule.SkillAlertRule (POS: Alert rule configuration)
- myrm_agent_harness.agent.skills.optimization.types.SkillQualityScore (POS: Quality score)

[OUTPUT]
- SkillQualityAlertWebhook: Webhook handler with multi-channel support

[POS]
Business layer proactive monitoring capability.
Features:
1. Configurable per-skill alert thresholds
2. Multi-channel notifications (Slack/Discord/Email/HTTP)
3. Rate limiting (max 1 alert per skill per hour)
4. Graceful degradation (failed channels logged, don't block)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from myrm_agent_harness.agent.skills.optimization.types import SkillQualityScore

    from app.database.models.skill_alert_rule import SkillAlertRule

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


class SkillQualityAlertWebhook:
    """Skill quality alert webhook with configurable rules

    Proactive monitoring system that sends alerts when skill quality drops
    below configured thresholds. Supports multiple notification channels.

    Features:
    - Per-skill configurable thresholds (core skills vs regular skills)
    - Multi-channel support (Slack, Discord, Email, HTTP)
    - Rate limiting (max 1 alert per skill per hour)
    - Graceful degradation (failed channels don't block)
    - Database-backed configuration (SkillAlertRule model)

    Args:
        db_session_factory: AsyncSession factory for database access
        rate_limit_seconds: Rate limit per skill (default: 3600 = 1h)

    Example:
        ```python
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        from app.services.skills.quality_alert_webhook import SkillQualityAlertWebhook

        engine = create_async_engine("sqlite+aiosqlite:///app.db")
        session_factory = async_sessionmaker(engine)

        webhook = SkillQualityAlertWebhook(session_factory)

        # Check and send alert
        alert_sent = await webhook.check_and_alert(
            skill_id="pdf-generator",
            latest_score=SkillQualityScore(overall_score=0.45, ...),
        )

        if alert_sent:
            logger.info("Alert sent to configured channels")
        ```
    """

    def __init__(
        self,
        db_session_factory: async_sessionmaker[AsyncSession],
        rate_limit_seconds: int = 3600,
    ) -> None:
        self.db_session_factory = db_session_factory
        self.rate_limit_seconds = rate_limit_seconds
        self._last_alerts: dict[str, datetime] = {}

    async def check_and_alert(
        self,
        skill_id: str,
        latest_score: SkillQualityScore,
    ) -> bool:
        """Check quality and send alert if threshold breached

        Args:
            skill_id: Skill identifier
            latest_score: Latest quality score

        Returns:
            True if alert sent, False otherwise
        """
        rule = await self._get_alert_rule(skill_id)

        if not rule or not rule.enabled:
            logger.debug(f"Alert disabled for skill {skill_id}")
            return False

        if latest_score.overall_score >= rule.quality_threshold:
            logger.debug(f"Quality {latest_score.overall_score:.2f} >= threshold {rule.quality_threshold:.2f}, no alert")
            return False

        last_alert = self._last_alerts.get(skill_id)
        if last_alert:
            elapsed = (datetime.now() - last_alert).total_seconds()
            if elapsed < self.rate_limit_seconds:
                logger.info(f"Alert rate-limited for {skill_id}: {elapsed:.0f}s < {self.rate_limit_seconds}s")
                return False

        await self._send_alert(skill_id, latest_score, rule)
        self._last_alerts[skill_id] = datetime.now()
        logger.info(
            f"Alert sent for skill {skill_id}: quality {latest_score.overall_score:.2f} < threshold {rule.quality_threshold:.2f}"
        )

        return True

    async def _get_alert_rule(self, skill_id: str) -> SkillAlertRule | None:
        """Get alert rule from database

        Args:
            skill_id: Skill identifier

        Returns:
            SkillAlertRule if exists, None otherwise
        """
        try:
            from app.database.models.skill_alert_rule import SkillAlertRule

            async with self.db_session_factory() as session:
                loaded: SkillAlertRule | None = await session.get(SkillAlertRule, skill_id)
                return loaded
        except Exception as e:
            logger.error(f"Failed to fetch alert rule for {skill_id}: {e}")
            return None

    async def _send_alert(
        self,
        skill_id: str,
        score: SkillQualityScore,
        rule: SkillAlertRule,
    ) -> None:
        """Send alert to configured channels

        Args:
            skill_id: Skill identifier
            score: Quality score that triggered alert
            rule: Alert rule configuration
        """
        message = self._format_alert_message(skill_id, score, rule)

        for channel in rule.channels:
            try:
                if channel == "slack" and rule.slack_webhook_url:
                    await self._send_slack(message, rule.slack_webhook_url)
                    logger.info(f"Slack alert sent for {skill_id}")
                elif channel == "discord" and rule.discord_webhook_url:
                    await self._send_discord(message, rule.discord_webhook_url)
                    logger.info(f"Discord alert sent for {skill_id}")
                elif channel == "email" and rule.email_recipients:
                    await self._send_email(message, rule.email_recipients)
                    logger.info(f"Email alert sent for {skill_id}")
                elif channel == "http" and rule.http_webhook_url:
                    await self._send_http(message, rule.http_webhook_url, skill_id, score)
                    logger.info(f"HTTP alert sent for {skill_id}")
                else:
                    logger.warning(f"Channel {channel} not configured for {skill_id}")
            except Exception as e:
                logger.error(f"Failed to send alert to {channel} for {skill_id}: {e}")

    @staticmethod
    def _format_alert_message(
        skill_id: str,
        score: SkillQualityScore,
        rule: SkillAlertRule,
    ) -> str:
        """Format alert message

        Args:
            skill_id: Skill identifier
            score: Quality score
            rule: Alert rule

        Returns:
            Formatted alert message
        """
        return (
            f"🚨 Skill Quality Alert\n"
            f"\n"
            f"**Skill**: {skill_id}\n"
            f"**Quality Score**: {score.overall_score:.2f} (Threshold: {rule.quality_threshold:.2f})\n"
            f"**Success Rate**: {score.success_rate:.2f}\n"
            f"**Token Efficiency**: {score.token_efficiency:.2f}\n"
            f"**Execution Time**: {score.execution_time:.2f}s\n"
            f"**User Satisfaction**: {score.user_satisfaction:.2f}\n"
            f"\n"
            f"🔍 Please investigate and optimize this skill.\n"
        )

    async def _send_slack(self, message: str, webhook_url: str) -> None:
        """Send alert to Slack

        Args:
            message: Alert message
            webhook_url: Slack webhook URL
        """
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                webhook_url,
                json={"text": message},
                headers={"Content-Type": "application/json"},
            )

    async def _send_discord(self, message: str, webhook_url: str) -> None:
        """Send alert to Discord

        Args:
            message: Alert message
            webhook_url: Discord webhook URL
        """
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                webhook_url,
                json={"content": message},
                headers={"Content-Type": "application/json"},
            )

    async def _send_email(self, message: str, recipients: list[str]) -> None:
        """Send alert via email

        Args:
            message: Alert message
            recipients: List of email addresses

        Note:
            Email sending requires SMTP configuration.
            This is a placeholder that logs the message.
            Integrate with SendGrid/SMTP in production.
        """
        logger.info(f"Email alert (placeholder): recipients={recipients}, message={message}")

    async def _send_http(
        self,
        message: str,
        webhook_url: str,
        skill_id: str,
        score: SkillQualityScore,
    ) -> None:
        """Send alert to custom HTTP endpoint

        Args:
            message: Alert message
            webhook_url: HTTP webhook URL
            skill_id: Skill identifier
            score: Quality score
        """
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                webhook_url,
                json={
                    "type": "skill_quality_alert",
                    "skill_id": skill_id,
                    "message": message,
                    "quality_score": {
                        "overall_score": score.overall_score,
                        "success_rate": score.success_rate,
                        "token_efficiency": score.token_efficiency,
                        "execution_time": score.execution_time,
                        "user_satisfaction": score.user_satisfaction,
                    },
                    "timestamp": datetime.now().isoformat(),
                },
                headers={"Content-Type": "application/json"},
            )
