"""实时告警通知

基于bash审计异常检测结果，发送告警通知。
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AlertConfig:
    """告警配置"""

    webhook_url: str | None = None
    slack_webhook: str | None = None
    email_recipients: list[str] | None = None


class BashAuditAlertNotifier:
    """Bash审计告警通知器"""

    def __init__(self, config: AlertConfig) -> None:
        self._config = config

    async def send_alert(self, alert_type: str, severity: str, message: str, details: dict[str, object]) -> bool:
        """发送告警通知

        Args:
            alert_type: 告警类型
            severity: 严重程度
            message: 告警消息
            details: 详细信息

        Returns:
            是否发送成功
        """
        # Webhook通知
        if self._config.webhook_url:
            success = await self._send_webhook(alert_type, severity, message, details)
            if success:
                logger.info(f"Sent alert via webhook: {alert_type}")
                return True

        # Slack通知
        if self._config.slack_webhook:
            success = await self._send_slack(alert_type, severity, message, details)
            if success:
                logger.info(f"Sent alert via Slack: {alert_type}")
                return True

        # Email通知（TODO：需要集成SMTP）
        if self._config.email_recipients:
            logger.info(f"Email alert (not implemented): {alert_type}")

        return False

    async def _send_webhook(self, alert_type: str, severity: str, message: str, details: dict[str, object]) -> bool:
        """发送Webhook告警"""
        try:
            import aiohttp

            payload = {
                "alert_type": alert_type,
                "severity": severity,
                "message": message,
                "details": details,
                "timestamp": __import__("time").time(),
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    str(self._config.webhook_url),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    return response.status == 200
        except Exception as e:
            logger.error(f"Failed to send webhook alert: {e}")
            return False

    async def _send_slack(self, alert_type: str, severity: str, message: str, details: dict[str, object]) -> bool:
        """发送Slack告警"""
        try:
            import aiohttp

            # Slack Webhook格式
            severity_emoji = {
                "LOW": ":information_source:",
                "MEDIUM": ":warning:",
                "HIGH": ":rotating_light:",
            }

            text = f"{severity_emoji.get(severity, ':bell:')} *Bash Audit Alert*\n\n"
            text += f"*Type:* {alert_type}\n"
            text += f"*Severity:* {severity}\n"
            text += f"*Message:* {message}\n\n"
            text += "*Details:*\n```\n"
            for key, value in details.items():
                text += f"{key}: {value}\n"
            text += "```"

            payload = {"text": text}

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    str(self._config.slack_webhook),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    return response.status == 200
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")
            return False
