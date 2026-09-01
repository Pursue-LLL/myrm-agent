"""Notifications package — event-driven IM notification dispatch and adaptive card formatting."""

from .adaptive_cards import FormattedNotification, format_legacy_text, format_notification
from .dispatcher import NotificationDispatcher, NotificationTarget

__all__ = [
    "FormattedNotification",
    "NotificationDispatcher",
    "NotificationTarget",
    "format_legacy_text",
    "format_notification",
]
