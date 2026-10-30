"""Architecture test: TelegramChannel mixin MRO must route _pre_emit_hook to hooks and collect_issues to diagnostics."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.channels.providers.telegram.channel import TelegramChannel
from app.channels.providers.telegram.diagnostics import TelegramDiagnosticsMixin
from app.channels.providers.telegram.hooks import TelegramHooksMixin
from app.channels.providers.telegram.inbound import TelegramInboundMixin
from app.channels.providers.telegram.inbound_message import TelegramMessageParserMixin
from app.channels.providers.telegram.inbound_poll import TelegramPollingMixin
from app.channels.providers.telegram.topics import TelegramTopicsMixin

_TELEGRAM_DIR = Path(__file__).resolve().parent.parent.parent / "app" / "channels" / "providers" / "telegram"
_INBOUND_MODULES = ("inbound.py", "inbound_message.py", "inbound_poll.py")
_INBOUND_MIXINS = (TelegramInboundMixin, TelegramMessageParserMixin, TelegramPollingMixin)


@pytest.mark.architecture
def test_telegram_pre_emit_hook_resolves_to_hooks_mixin() -> None:
    """Inbound must not shadow agent-command interception on TelegramChannel."""
    owner = next(cls for cls in TelegramChannel.__mro__ if "_pre_emit_hook" in cls.__dict__)
    assert owner is TelegramHooksMixin


@pytest.mark.architecture
def test_telegram_collect_issues_resolves_to_diagnostics_mixin() -> None:
    """BaseChannel's generic collect_issues must not shadow the Telegram diagnostics."""
    owner = next(cls for cls in TelegramChannel.__mro__ if "collect_issues" in cls.__dict__)
    assert owner is TelegramDiagnosticsMixin


@pytest.mark.architecture
@pytest.mark.parametrize("mixin", _INBOUND_MIXINS, ids=lambda cls: cls.__name__)
def test_telegram_inbound_mixins_do_not_define_pre_emit_hook(mixin: type) -> None:
    """The inbound mixins dispatch, parse and poll only; hooks own _pre_emit_hook."""
    assert "_pre_emit_hook" not in mixin.__dict__


@pytest.mark.architecture
@pytest.mark.parametrize("module", _INBOUND_MODULES)
def test_telegram_inbound_source_has_no_pre_emit_hook_definition(module: str) -> None:
    """Static guard: no inbound module may reintroduce a passthrough _pre_emit_hook.

    Only a definition in a class body counts; the ``if TYPE_CHECKING`` declaration that tells the type checker
    the host provides the hook is nested one level deeper and never exists at runtime.
    """
    tree = ast.parse((_TELEGRAM_DIR / module).read_text(encoding="utf-8"))
    defined = [
        f"{cls.name}.{node.name}"
        for cls in tree.body
        if isinstance(cls, ast.ClassDef)
        for node in cls.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == "_pre_emit_hook"
    ]
    assert defined == []


@pytest.mark.architecture
def test_telegram_channel_mro_orders_topics_before_hooks() -> None:
    """Hooks._apply_auto_topic calls TopicsMixin.ensure_topic_for_user via MRO."""
    mro = TelegramChannel.__mro__
    assert mro.index(TelegramTopicsMixin) < mro.index(TelegramHooksMixin)
