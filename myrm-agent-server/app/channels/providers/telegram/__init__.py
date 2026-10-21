"""Telegram channel provider — Bot API bidirectional messaging.

Public API:
    TelegramChannel   — main channel class (polling + webhook)
    TelegramClient    — async Bot API client
    TelegramApiError  — API error exception
    BotCommand        — command registration dataclass
    md_to_telegram_html — Markdown -> Telegram HTML converter
    split_message     — message splitting utility
    build_inline_keyboard — inline keyboard builder
"""

from .api import TelegramApiError, TelegramClient
from .channel import TelegramChannel
from .helpers import BotCommand, build_inline_keyboard
from .html_converter import md_to_telegram_html, split_message

__all__ = [
    "BotCommand",
    "TelegramApiError",
    "TelegramChannel",
    "TelegramClient",
    "build_inline_keyboard",
    "md_to_telegram_html",
    "split_message",
]
