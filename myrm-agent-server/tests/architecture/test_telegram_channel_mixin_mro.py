"""Architecture test: TelegramChannel mixin MRO must route _pre_emit_hook to hooks."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.channels.providers.telegram.channel import TelegramChannel
from app.channels.providers.telegram.hooks import TelegramHooksMixin
from app.channels.providers.telegram.inbound import TelegramInboundMixin
from app.channels.providers.telegram.topics import TelegramTopicsMixin

_TELEGRAM_INBOUND_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "app"
    / "channels"
    / "providers"
    / "telegram"
    / "inbound.py"
)


@pytest.mark.architecture
def test_telegram_pre_emit_hook_resolves_to_hooks_mixin() -> None:
    """Inbound must not shadow agent-command interception on TelegramChannel."""
    assert TelegramChannel._pre_emit_hook is TelegramHooksMixin._pre_emit_hook


@pytest.mark.architecture
def test_telegram_inbound_mixin_does_not_define_pre_emit_hook() -> None:
    """TelegramInboundMixin is parse/poll only; hooks own _pre_emit_hook."""
    assert "_pre_emit_hook" not in TelegramInboundMixin.__dict__


@pytest.mark.architecture
def test_telegram_inbound_source_has_no_pre_emit_hook_definition() -> None:
    """Static guard: inbound.py must not reintroduce a passthrough _pre_emit_hook stub."""
    source = _TELEGRAM_INBOUND_PATH.read_text(encoding="utf-8")
    tree_body = source.split("class TelegramInboundMixin", 1)[-1]
    assert "def _pre_emit_hook" not in tree_body


@pytest.mark.architecture
def test_telegram_channel_mro_orders_topics_before_hooks() -> None:
    """Hooks._apply_auto_topic calls TopicsMixin.ensure_topic_for_user via MRO."""
    mro = TelegramChannel.__mro__
    assert mro.index(TelegramTopicsMixin) < mro.index(TelegramHooksMixin)
