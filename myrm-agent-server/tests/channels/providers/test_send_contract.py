"""Static guards for the provider ``send()`` contract.

``send()`` either delivers or raises: a failure swallowed into ``return None`` leaves the message bus
believing the message was delivered, and a provider that can never return a message id has to say so, or
``delivery_unconfirmed`` would dead-letter every message it did deliver.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

import pytest

from app.channels.core.base import BaseChannel
from app.channels.providers.registry import _BUILTIN_SPECS, get_channel_class_safe


def _provider_classes() -> list[tuple[str, type[BaseChannel]]]:
    loaded = ((name, get_channel_class_safe(name)) for name in sorted(_BUILTIN_SPECS))
    return [(name, cls) for name, cls in loaded if cls is not None]


def _send_tree(cls: type[BaseChannel]) -> ast.AST:
    return ast.parse(textwrap.dedent(inspect.getsource(cls.send)))


def _returns_none(node: ast.Return) -> bool:
    return node.value is None or (isinstance(node.value, ast.Constant) and node.value.value is None)


@pytest.mark.parametrize(("name", "cls"), _provider_classes(), ids=lambda value: value if isinstance(value, str) else "")
def test_provider_that_never_returns_an_id_declares_message_ids_false(name: str, cls: type[BaseChannel]) -> None:
    returns_a_value = any(isinstance(node, ast.Return) and not _returns_none(node) for node in ast.walk(_send_tree(cls)))

    assert returns_a_value or not cls.capabilities.message_ids, (
        f"{name}: send() never returns a message id, so capabilities must declare message_ids=False"
    )


@pytest.mark.parametrize(("name", "cls"), _provider_classes(), ids=lambda value: value if isinstance(value, str) else "")
def test_send_never_swallows_a_failure_into_none(name: str, cls: type[BaseChannel]) -> None:
    swallowed = [
        node.lineno
        for handler in ast.walk(_send_tree(cls))
        if isinstance(handler, ast.ExceptHandler)
        for node in ast.walk(handler)
        if isinstance(node, ast.Return) and _returns_none(node)
    ]

    assert not swallowed, (
        f"{name}: send() returns None from an except handler (relative lines {swallowed}); raise ChannelSendError instead"
    )
