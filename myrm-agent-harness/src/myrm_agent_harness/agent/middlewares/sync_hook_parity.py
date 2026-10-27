"""Sync wrap hooks for middlewares that define only the async variant.

LangChain puts a middleware in the sync tool and model call chains when its class defines either variant of
``wrap_tool_call`` / ``wrap_model_call``, and the default sync variant raises ``NotImplementedError``. A sync run
(the signoff clarify pool warm executes ``ask_question_tool`` through the sync ToolNode) therefore fails on a
middleware that has only ``awrap_tool_call`` / ``awrap_model_call``. ``apply_sync_hook_parity`` gives such a
middleware a pass-through sync variant and leaves every other hook as the middleware defined it.

LangChain reads the hooks from the middleware's class (``m.__class__.before_model`` ...), and builds one graph node
for each ``before_model`` / ``after_model`` it finds there. A wrapper object that forwards attributes would hide the
wrapped middleware's own hooks from that check, so the pass-through goes onto a subclass of the middleware's class
and the instance moves onto it: same object, same ``isinstance`` answers, same hooks.

[INPUT]
- langchain.agents.middleware::AgentMiddleware (POS: Hook defaults the missing sync variants are detected against.)

[OUTPUT]
- apply_sync_hook_parity: Gives every middleware in a list the sync wrap hooks it lacks, in place.

[POS]
Final step of the middleware stack build; keeps sync runs working next to async-only wrap hooks.
"""

from __future__ import annotations

from collections.abc import Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

# The subclass each middleware class runs as; one per class, shared by its instances.
_PARITY_CLASSES: dict[type[AgentMiddleware], type[AgentMiddleware]] = {}


def _sync_wrap_tool_call(
    self: AgentMiddleware,
    request: ToolCallRequest,
    handler: Callable[[ToolCallRequest], ToolMessage | Command[object]],
) -> ToolMessage | Command[object]:
    return handler(request)


def _sync_wrap_model_call(
    self: AgentMiddleware,
    request: ModelRequest,
    handler: Callable[[ModelRequest], ModelResponse],
) -> ModelResponse:
    return handler(request)


def _missing_sync_hooks(cls: type[AgentMiddleware]) -> dict[str, Callable[..., object]]:
    """The sync wrap hooks *cls* needs: the ones it defines only in the async form."""
    missing: dict[str, Callable[..., object]] = {}
    if (
        cls.awrap_tool_call is not AgentMiddleware.awrap_tool_call
        and cls.wrap_tool_call is AgentMiddleware.wrap_tool_call
    ):
        missing["wrap_tool_call"] = _sync_wrap_tool_call
    if (
        cls.awrap_model_call is not AgentMiddleware.awrap_model_call
        and cls.wrap_model_call is AgentMiddleware.wrap_model_call
    ):
        missing["wrap_model_call"] = _sync_wrap_model_call
    return missing


def _with_sync_hooks(cls: type[AgentMiddleware]) -> type[AgentMiddleware]:
    """*cls* itself when it needs nothing, else a subclass of it carrying the missing sync hooks."""
    if cls not in _PARITY_CLASSES:
        missing = _missing_sync_hooks(cls)
        _PARITY_CLASSES[cls] = (
            type(cls.__name__, (cls,), {**missing, "__module__": cls.__module__, "__qualname__": cls.__qualname__})
            if missing
            else cls
        )
    return _PARITY_CLASSES[cls]


def apply_sync_hook_parity(middlewares: list[object]) -> list[object]:
    """Give each middleware the sync wrap hooks it lacks, so sync ToolNode and model paths do not raise."""
    for middleware in middlewares:
        if isinstance(middleware, AgentMiddleware):
            middleware.__class__ = _with_sync_hooks(type(middleware))
    return middlewares


__all__ = ["apply_sync_hook_parity"]
