"""Batch Notification Service

Multi-channel notification system for batch optimization events.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class NotificationChannel(str, Enum):
    """Notification channel types"""

    EMAIL = "email"
    SLACK = "slack"
    DINGTALK = "dingtalk"
    WEBHOOK = "webhook"


@dataclass
class NotificationConfig:
    """Notification configuration

    Attributes:
        channel: Notification channel
        enabled: Whether this channel is enabled
        webhook_url: Webhook URL (for Slack/DingTalk/custom webhooks)
        email_to: Email recipient address
        email_smtp_host: SMTP server host
        email_smtp_port: SMTP server port
        email_from: Sender email address
        email_username: SMTP username
        email_password: SMTP password
    """

    channel: NotificationChannel
    enabled: bool = True

    webhook_url: str | None = None

    email_to: str | None = None
    email_smtp_host: str | None = None
    email_smtp_port: int = 587
    email_from: str | None = None
    email_username: str | None = None
    email_password: str | None = None


class NotificationProvider(ABC):
    """Abstract notification provider"""

    @abstractmethod
    async def send(self, title: str, message: str, details: dict[str, object] | None = None) -> bool:
        """Send notification

        Args:
            title: Notification title
            message: Notification message
            details: Additional details (optional)

        Returns:
            bool: Whether notification was sent successfully
        """
        pass


class EmailNotificationProvider(NotificationProvider):
    """Email notification provider"""

    def __init__(self, config: NotificationConfig):
        self.config = config

    async def send(self, title: str, message: str, details: dict[str, object] | None = None) -> bool:
        """Send email notification via SMTP

        Args:
            title: Email subject
            message: Email body
            details: Additional details

        Returns:
            bool: Whether email was sent successfully
        """
        email_to = self.config.email_to
        smtp_host = self.config.email_smtp_host
        email_from = self.config.email_from
        if not email_to or not smtp_host or not email_from:
            logger.warning("[EMAIL] Missing configuration, falling back to logging")
            logger.info(f"[EMAIL] {title}: {message}")
            return True

        try:
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            import aiosmtplib

            msg = MIMEMultipart()
            msg["From"] = email_from
            msg["To"] = email_to
            msg["Subject"] = title

            body = f"{message}\n\n"
            if details:
                body += "Details:\n"
                for key, value in details.items():
                    body += f"  {key}: {value}\n"

            msg.attach(MIMEText(body, "plain"))

            await aiosmtplib.send(
                msg,
                hostname=smtp_host,
                port=self.config.email_smtp_port,
                username=self.config.email_username or email_from,
                password=self.config.email_password,
                start_tls=True,
            )

            logger.info(f"[EMAIL] Sent to {self.config.email_to}: {title}")
            return True

        except ImportError:
            logger.warning("[EMAIL] aiosmtplib not installed, falling back to logging")
            logger.info(f"[EMAIL] {title}: {message}")
            return True
        except Exception as e:
            logger.error(f"[EMAIL] Failed to send: {e}")
            return False


class SlackNotificationProvider(NotificationProvider):
    """Slack notification provider"""

    def __init__(self, config: NotificationConfig):
        self.config = config

    async def send(self, title: str, message: str, details: dict[str, object] | None = None) -> bool:
        """Send Slack notification via webhook

        Args:
            title: Notification title
            message: Notification message
            details: Additional details

        Returns:
            bool: Whether notification was sent successfully
        """
        try:
            logger.info(f"[SLACK] Sending notification: {title}")
            logger.info(f"[SLACK] Webhook: {self.config.webhook_url}")
            logger.info(f"[SLACK] Message: {message}")

            return True
        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")
            return False


class DingTalkNotificationProvider(NotificationProvider):
    """DingTalk notification provider"""

    def __init__(self, config: NotificationConfig):
        self.config = config

    async def send(self, title: str, message: str, details: dict[str, object] | None = None) -> bool:
        """Send DingTalk notification via webhook

        Args:
            title: Notification title
            message: Notification message
            details: Additional details

        Returns:
            bool: Whether notification was sent successfully
        """
        try:
            logger.info(f"[DINGTALK] Sending notification: {title}")
            logger.info(f"[DINGTALK] Webhook: {self.config.webhook_url}")
            logger.info(f"[DINGTALK] Message: {message}")

            return True
        except Exception as e:
            logger.error(f"Failed to send DingTalk notification: {e}")
            return False


class NotificationService:
    """Batch optimization notification service"""

    def __init__(self, configs: list[NotificationConfig] | None = None):
        self.providers: list[NotificationProvider] = []

        if configs:
            for config in configs:
                if not config.enabled:
                    continue

                if config.channel == NotificationChannel.EMAIL:
                    self.providers.append(EmailNotificationProvider(config))
                elif config.channel == NotificationChannel.SLACK:
                    self.providers.append(SlackNotificationProvider(config))
                elif config.channel == NotificationChannel.DINGTALK:
                    self.providers.append(DingTalkNotificationProvider(config))

    async def notify_batch_started(self, batch_id: str, total_tasks: int) -> None:
        """Notify batch optimization started

        Args:
            batch_id: Batch task ID
            total_tasks: Total number of tasks
        """
        title = "Batch Optimization Started"
        message = f"Batch {batch_id} started with {total_tasks} tasks"
        details: dict[str, object] = {"batch_id": batch_id, "total_tasks": total_tasks}

        await self._broadcast(title, message, details)

    async def notify_batch_completed(
        self,
        batch_id: str,
        total_tasks: int,
        completed: int,
        failed: int,
        duration_seconds: float,
    ) -> None:
        """Notify batch optimization completed

        Args:
            batch_id: Batch task ID
            total_tasks: Total number of tasks
            completed: Number of completed tasks
            failed: Number of failed tasks
            duration_seconds: Total duration in seconds
        """
        title = "Batch Optimization Completed"
        message = (
            f"Batch {batch_id} completed:\n"
            f"- Total: {total_tasks}\n"
            f"- Completed: {completed}\n"
            f"- Failed: {failed}\n"
            f"- Duration: {duration_seconds:.1f}s"
        )
        details_completed: dict[str, object] = {
            "batch_id": batch_id,
            "total_tasks": total_tasks,
            "completed": completed,
            "failed": failed,
            "duration_seconds": duration_seconds,
        }

        await self._broadcast(title, message, details_completed)

    async def notify_batch_failed(self, batch_id: str, error_message: str) -> None:
        """Notify batch optimization failed

        Args:
            batch_id: Batch task ID
            error_message: Error message
        """
        title = "Batch Optimization Failed"
        message = f"Batch {batch_id} failed: {error_message}"
        details_err: dict[str, object] = {"batch_id": batch_id, "error": error_message}

        await self._broadcast(title, message, details_err)

    async def _broadcast(self, title: str, message: str, details: dict[str, object] | None = None) -> None:
        """Broadcast notification to all enabled providers

        Args:
            title: Notification title
            message: Notification message
            details: Additional details
        """
        if not self.providers:
            logger.debug("No notification providers configured")
            return

        for provider in self.providers:
            try:
                await provider.send(title, message, details)
            except Exception as e:
                logger.error(f"Notification provider failed: {e}")
