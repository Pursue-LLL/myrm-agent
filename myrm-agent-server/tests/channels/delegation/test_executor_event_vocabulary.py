"""The executor's event vocabulary is one contract: the protocol declares it, the executor yields it, the coordinator consumes it.

A delegated task is built from the stream's events alone. An event type the executor starts to yield but the protocol and
the coordinator do not know would be silently dropped from every delegated run.
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Callable

from app.channels import types as channel_types
from app.channels.delegation import delegation_coordinator
from app.channels.protocols.agent import AgentExecutor
from app.core.channel_bridge.agent_executor.executor import ChannelAgentExecutor

_CONSUMED_BY_DELEGATION = {channel_types.ProgressUpdate, channel_types.StreamingText, channel_types.OutboundMessage}
# Declared by the protocol for the live message of a foreground chat; a delegated task has none.
_IGNORED_BY_DELEGATION = {channel_types.FissionTopologyUpdate}


def _declared_events(execute_stream: Callable[..., object]) -> set[type]:
    """The event classes named in the return annotation of ``execute_stream``."""
    annotation = inspect.signature(execute_stream).return_annotation
    names = {node.id for node in ast.walk(ast.parse(annotation, mode="eval")) if isinstance(node, ast.Name)}
    names.discard("AsyncGenerator")
    unknown = {name for name in names if not hasattr(channel_types, name)}
    assert not unknown, f"{unknown} is not a channel type this contract knows"
    return {getattr(channel_types, name) for name in names}


def test_the_protocol_declares_every_event_the_executor_yields() -> None:
    declared = _declared_events(AgentExecutor.execute_stream)
    yielded = _declared_events(ChannelAgentExecutor.execute_stream)

    assert yielded <= declared, f"the protocol does not declare {yielded - declared}"


def test_the_coordinator_handles_or_deliberately_ignores_every_declared_event() -> None:
    assert _declared_events(AgentExecutor.execute_stream) == _CONSUMED_BY_DELEGATION | _IGNORED_BY_DELEGATION
    source = inspect.getsource(delegation_coordinator)
    for consumed in _CONSUMED_BY_DELEGATION:
        assert f"isinstance(event, {consumed.__name__})" in source
