"""A model call as the memory-context middleware sees it, without a running agent: its request and its manager.

[OUTPUT]
- make_request: a ``ModelRequest`` stand-in with the messages, the bound tools and the run context the middleware reads, and an ``override`` that rebuilds it like the real one
- bound_manager: a context manager that makes a given object the memory manager the middleware reads (``None``: a run without one)

[POS]
Harness pytest-only helper shared by the memory-context middleware tests, so each one states the request it needs
and the manager it runs under, and not how either is assembled.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from langchain_core.messages import AnyMessage, HumanMessage

_MANAGER_GETTER = "myrm_agent_harness.agent.skill_agent.context.get_memory_manager"


@contextmanager
def bound_manager(manager: object) -> Iterator[None]:
    """Make ``manager`` the memory manager of the run for the length of the ``with`` block."""
    with patch(_MANAGER_GETTER, return_value=manager):
        yield


def make_request(
    *,
    messages: list[AnyMessage] | None = None,
    has_runtime_context: bool = True,
    tools: list[object] | None = None,
) -> MagicMock:
    """Build a minimal mock ModelRequest.

    Defaults to HYBRID-like tools (``memory_search_tool`` bound on turn one, as in the default builtin set) so the warm
    and cold injection paths run with memory-search guidance enabled.
    """
    req = MagicMock()
    req.messages = messages or [HumanMessage(content="Hello")]

    if tools is None:
        tools = [SimpleNamespace(name="memory_search_tool")]
    req.tools = tools

    if has_runtime_context:
        req.runtime = MagicMock()
        req.runtime.context = {"some": "context"}
    else:
        req.runtime = None

    # The real ModelRequest.override rebuilds the request with dataclasses.replace, which keeps the tools.
    req.override = MagicMock(side_effect=lambda **kwargs: MagicMock(tools=tools, **kwargs))
    return req
