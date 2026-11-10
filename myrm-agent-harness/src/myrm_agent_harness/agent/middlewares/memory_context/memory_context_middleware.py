"""Memory context injection middleware.

Injects the user's stored memory — profile, self-instructions, behavioral rules (VETO rules first), tool guidance,
working state — as one ``<user_memory_context>`` SystemMessage immediately after the leading System prompts
(prompt-cache friendly). Learned facts are never injected: the model retrieves them through
``memory_search_tool(corpus=memory)``, which keeps the prompt prefix stable across turns. A user with no stored memory
gets the cold-start Discovery Mode block instead.

Respects RecallMode: TOOLS skips injection entirely.
The block is request-local: it is rebuilt for every model call and never persisted to the thread. It is built from the
run context's ``memory_brief_snapshot``; a run without one loads ``manager.get_context`` on the turn's first model
call and the turn's later calls reuse that load, so a memory saved mid-turn reaches the next turn and no two calls of
one turn see different memory. A turn starts at the user's own latest message in the thread; a notice the runtime
appends and a rewrite an outer middleware makes to the request start none. Neither the snapshot nor the loaded
context is written to: tool guidance, which depends on the tools bound to the call, goes into a copy. A call is
skipped (and a warning logged) only when the request already carries a block this middleware built, recognised by its
flag rather than by its text.

Design message order:

    System Prompt (cross-user stable) …
    <user_instructions> …
    <user_memory_context> … profile / rules / guidance + Memory Search cues …
    first real user HumanMessage …

[INPUT]
- toolkits.memory.config::RecallMode, RetrievalConfig (POS: Memory configuration — functional switches and retrieval params only.)
- toolkits.memory.manager::MemoryManager (POS: Unified memory manager and core facade of the Memory Toolkit. Orchestrates all memory operations via pure dependency injection — no concrete backends, only protocols.)
- toolkits.memory.tool_guidance::ToolGuidanceItem, synthesize_tool_guidance (POS: Tool memory procedural contract & synthesis domain layer.)
- core.message_origin::is_user_authored_human_message (POS: Message-provenance primitives shared by the approval, security, memory-context and context-management layers.)
- .memory_context_format::MemoryBlock, MEMORY_BLOCK_BUDGET_CHARS, _format_memory_context, _has_memory_context, _memory_context_message, _bound_tool_names, _memory_search_tool_bound (POS: Memory block renderer for MemoryContextMiddleware: renders the block text and builds and recognises the flagged message that carries it.)

[OUTPUT]
- memory_context_middleware: AgentMiddleware — memory block injection with a unified budget, idempotent per request.

[POS]
Memory context injection middleware bridging MemoryManager snapshots into the model prefix.
"""

from __future__ import annotations

import asyncio
import copy
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, AnyMessage, SystemMessage

from myrm_agent_harness.core.message_origin import is_user_authored_human_message
from myrm_agent_harness.toolkits.memory.config import RecallMode, RetrievalConfig
from myrm_agent_harness.toolkits.memory.tool_guidance import (
    ToolGuidanceItem,
    synthesize_tool_guidance,
)

from .memory_context_format import (
    MEMORY_BLOCK_BUDGET_CHARS,
    MemoryBlock,
    _bound_tool_names,
    _format_memory_context,
    _has_memory_context,
    _memory_context_message,
    _memory_search_tool_bound,
)

if TYPE_CHECKING:
    from myrm_agent_harness.agent.skill_agent.context import (
        MemoryInjectionReason,
        MemoryInjectionSource,
        MemoryInjectionState,
        MemoryRuntimeInjection,
    )
    from myrm_agent_harness.toolkits.memory.manager import MemoryManager

logger = logging.getLogger(__name__)

_DEFAULT_LOAD_TIMEOUT_SECONDS = RetrievalConfig().timeout_seconds

# Slot of the run-context dict that carries a turn's loaded memory context to the turn's later model calls.
_TURN_LOAD_SLOT = "_memory_context_turn_load"


def _retrieval_timeout_seconds(manager: object) -> float:
    """Wall-clock ceiling for memory-context loading, from manager config or default."""
    config = getattr(manager, "_config", None)
    retrieval = getattr(config, "retrieval", None)
    timeout = getattr(retrieval, "timeout_seconds", None)
    if isinstance(timeout, (int, float)) and not isinstance(timeout, bool) and timeout > 0:
        return float(timeout)
    return _DEFAULT_LOAD_TIMEOUT_SECONDS


def _set_memory_injection_status(
    *,
    state: MemoryInjectionState,
    source: MemoryInjectionSource | None = None,
    reason: MemoryInjectionReason | None = None,
) -> None:
    from myrm_agent_harness.agent.skill_agent.context import (
        set_memory_runtime_budget,
        set_memory_runtime_injection,
    )

    payload: MemoryRuntimeInjection = {"state": state}
    if source is not None:
        payload["source"] = source
    if reason is not None:
        payload["reason"] = reason
    if state != "applied":
        # Prevent stale budget from previous turns leaking into current message_end.
        set_memory_runtime_budget(None)
    set_memory_runtime_injection(payload)


def _reset_memory_telemetry() -> None:
    """Drop the previous model call's budget and injection status, so an early exit never carries them over."""
    from myrm_agent_harness.agent.skill_agent.context import (
        set_memory_runtime_budget,
        set_memory_runtime_injection,
    )

    set_memory_runtime_budget(None)
    set_memory_runtime_injection(None)


def _prefixed_ai_message(msg: AIMessage) -> AIMessage | None:
    """``msg`` with its text led by ``[Agent: name]``, so the model can tell the agents of a shared thread apart.

    ``None`` when the message needs no change: it has no text block to lead, or the tag is already there.
    """
    prefix = f"[Agent: {msg.name}]\n"
    content = msg.content
    new_content: str | list[str | dict[str, object]]
    if isinstance(content, str):
        if content.startswith(prefix):
            return None
        new_content = f"{prefix}{content}"
    elif isinstance(content, list) and content:
        first_block = content[0]
        if not isinstance(first_block, dict) or first_block.get("type") != "text":
            return None
        first_text = first_block.get("text", "")
        if not isinstance(first_text, str) or first_text.startswith(prefix):
            return None
        led_block = copy.deepcopy(first_block)
        led_block["text"] = f"{prefix}{first_text}"
        new_content = [led_block, *copy.deepcopy(content[1:])]
    else:
        return None
    return AIMessage(
        content=new_content,
        name=msg.name,
        tool_calls=msg.tool_calls,
        additional_kwargs=msg.additional_kwargs,
        id=msg.id,
    )


def _attribute_ai_messages(request: ModelRequest) -> ModelRequest:
    """``request`` with every named AI message led by its agent tag; ``request`` itself when none needs one."""
    messages = list(request.messages)
    modified = False
    for idx, msg in enumerate(messages):
        if isinstance(msg, AIMessage) and msg.name:
            prefixed = _prefixed_ai_message(msg)
            if prefixed is not None:
                messages[idx] = prefixed
                modified = True
    return request.override(messages=messages) if modified else request


@dataclass(frozen=True)
class _StaticContext:
    """The outcome of loading the stable memory context: the context to render, or the reason there is none."""

    source: MemoryInjectionSource
    ctx: dict[str, object] | None = None
    skip_reason: MemoryInjectionReason | None = None


def _checked_static_context(raw: object, source: MemoryInjectionSource) -> _StaticContext:
    """``raw`` as a loadable context, or the reason it cannot be rendered."""
    if isinstance(raw, BaseException):
        logger.warning("Static memory context failed: %s", raw)
        return _StaticContext(source, skip_reason="static_error")
    if not isinstance(raw, dict):
        logger.warning("Static memory context payload has unexpected type: %s", type(raw).__name__)
        return _StaticContext(source, skip_reason="invalid_static_payload")
    return _StaticContext(source, ctx=raw)


async def _live_load(manager: MemoryManager) -> _StaticContext:
    """Load the stable memory context from the manager, bounded by its retrieval timeout."""
    try:
        async with asyncio.timeout(_retrieval_timeout_seconds(manager)):
            loaded = await manager.get_context(
                include_profile=True,
                include_rules=True,
                include_agent_instructions=True,
            )
    except TimeoutError:
        logger.warning("Memory context load timed out; skipping memory injection")
        return _StaticContext("fallback", skip_reason="load_timeout")
    except Exception as e:
        logger.warning("Failed to load memory context: %s", e)
        return _StaticContext("fallback", skip_reason="load_error")
    return _checked_static_context(loaded, "fallback")


@dataclass(frozen=True)
class _TurnLoad:
    """What the first model call of a turn loaded, left in the run context for the turn's later calls."""

    turn_id: str
    loaded: _StaticContext


def _current_turn_id(messages: Sequence[AnyMessage]) -> str | None:
    """The id of the user's latest message: every model call of one turn, tool loop included, shares it.

    A notice the runtime appends mid-run (a recovery hint, a restore note) is not the user's message and starts no turn.
    """
    for message in reversed(messages):
        if is_user_authored_human_message(message):
            return message.id
    return None


def _thread_messages(request: ModelRequest) -> Sequence[AnyMessage]:
    """The conversation the graph holds, which the request-local rewrites of the outer middlewares never reach.

    Those rewrites change the request's messages from one call of a turn to the next: the circuit-breaker constraints
    are appended to every call, and the todo focus replaces the runtime notice at the tail on a run's first call only.
    A request built outside a graph run carries no thread, so its own messages stand in.
    """
    thread = request.state.get("messages")
    return thread if isinstance(thread, list) and thread else request.messages


async def _load_static_context(
    manager: MemoryManager, context: object, messages: Sequence[AnyMessage]
) -> _StaticContext:
    """The stable memory context of this model call.

    A run that prefetched a snapshot reads it. Otherwise the first call of a turn loads from the manager and the
    turn's later calls reuse that outcome: a memory the agent saves mid-turn reaches the model on the next turn and
    never splits one turn's prompt prefix, and a failed load is not retried (and waited for) on every call.
    """
    if not isinstance(context, dict):
        return await _live_load(manager)
    snapshot = context.get("memory_brief_snapshot")
    if isinstance(snapshot, dict):
        return _checked_static_context(snapshot.get("memory_ctx", {}), "snapshot")
    turn_id = _current_turn_id(messages)
    if turn_id is None:
        return await _live_load(manager)
    memo = context.get(_TURN_LOAD_SLOT)
    if isinstance(memo, _TurnLoad) and memo.turn_id == turn_id:
        return memo.loaded
    loaded = await _live_load(manager)
    context[_TURN_LOAD_SLOT] = _TurnLoad(turn_id, loaded)
    return loaded


def _context_with_tool_guidance(ctx: dict[str, object], request: ModelRequest) -> dict[str, object]:
    """A copy of ``ctx`` carrying the tool guidance of the tools this call binds.

    Every model call of the turn reads the same loaded context, and the guidance is picked per call from the tools
    that call binds: it goes into a copy, so one call's pick never reaches the next call or the snapshot.
    """
    memory_ctx = dict(ctx)
    raw_guidance_raw = memory_ctx.get("raw_tool_guidance_items")
    if isinstance(raw_guidance_raw, list) and raw_guidance_raw:
        raw_guidance = [g for g in raw_guidance_raw if isinstance(g, ToolGuidanceItem)]
        # A request that binds no named tool carries no scope: guidance for every tool is kept.
        tool_guidance_map = synthesize_tool_guidance(
            raw_guidance,
            target_tools=set(_bound_tool_names(request)) or None,
        )
        if tool_guidance_map:
            memory_ctx["tool_guidance"] = tool_guidance_map
    return memory_ctx


def _with_memory_block(messages: Sequence[AnyMessage], block: str) -> list[AnyMessage]:
    """``messages`` with the block after the leading system messages, so the cached prefix stays intact."""
    new_messages = list(messages)
    insert_idx = next((i for i, m in enumerate(new_messages) if not isinstance(m, SystemMessage)), len(new_messages))
    new_messages.insert(insert_idx, _memory_context_message(block))
    return new_messages


def _publish_budget(block: MemoryBlock) -> None:
    """Expose the block's budget use to the runner state for the UX progress bar.

    Reports how many rules actually reached the model, so a budget-trimmed prompt never reports the full configured
    rule count as if the model had obeyed all of them.
    """
    # Store normalized telemetry for server-side SSE/persistence hooks.
    from myrm_agent_harness.agent.skill_agent.context import (
        set_memory_runtime_budget,
    )

    set_memory_runtime_budget(
        {
            "used": block.budget_used_chars,
            "total": MEMORY_BLOCK_BUDGET_CHARS,
            "rulesConfigured": block.rules_configured,
            "rulesInjected": block.rules_injected,
            "rulesTruncated": block.rules_injected < block.rules_configured,
        }
    )


class MemoryContextMiddleware(AgentMiddleware):
    """Inject user memory context into every model call.

    The block is a ``SystemMessage`` inserted after the leading system messages. It is built from the per-turn
    ``memory_brief_snapshot`` of the run context when present, otherwise from the ``manager.get_context`` load of the
    turn's first model call; the manager is the one bound with ``set_memory_manager`` (MemoryManager with user_id
    bound).
    """

    name = "memory_context_middleware"

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        request = _attribute_ai_messages(request)
        # Always clear previous-turn telemetry first to avoid stale carry-over when
        # this turn exits early (e.g., missing manager/context).
        _reset_memory_telemetry()

        if _has_memory_context(request.messages):
            logger.warning("Memory context block already present in the request; skipping injection")
            _set_memory_injection_status(state="not_applied", reason="already_present")
            return await handler(request)

        context = getattr(request.runtime, "context", None) if request.runtime else None
        from myrm_agent_harness.agent.skill_agent.context import get_memory_manager

        manager: MemoryManager | None = get_memory_manager()
        if not manager:
            return await handler(request)

        _set_memory_injection_status(
            state="not_applied",
            reason="missing_context" if not context else "not_injected",
        )
        if not context:
            return await handler(request)

        if manager.recall_mode == RecallMode.TOOLS:
            _set_memory_injection_status(state="not_applied", reason="recall_mode_tools")
            return await handler(request)

        loaded = await _load_static_context(manager, context, _thread_messages(request))
        if loaded.ctx is None:
            _set_memory_injection_status(state="not_applied", reason=loaded.skip_reason)
            return await handler(request)

        memory_ctx = _context_with_tool_guidance(loaded.ctx, request)
        memory_search_enabled = _memory_search_tool_bound(request)
        block = _format_memory_context(memory_ctx, memory_search_enabled=memory_search_enabled)
        if not block.text:
            _set_memory_injection_status(state="not_applied", reason="empty_context")
            return await handler(request)

        new_messages = _with_memory_block(request.messages, block.text)
        _publish_budget(block)
        _set_memory_injection_status(state="applied", source=loaded.source)
        return await handler(request.override(messages=new_messages))


memory_context_middleware = MemoryContextMiddleware()
