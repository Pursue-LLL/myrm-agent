"""Inject Layer-1 base context at the tail of the user's latest message (prefix cache safe).

[INPUT]
- toolkits.memory.two_layer_dialectic.injector::TwoLayerContextInjector
- core.message_tail::append_block_to_last_user_message (POS: Tail-of-turn injection primitive: per-turn content lives only on the user's latest message so the SystemMessage and earlier history keep their prompt-cache prefix.)
- core.context_vars::chat_id_var
- core.message_origin::count_user_authored_messages, is_user_authored_human_message, last_user_authored_index (POS: Message-provenance primitives shared by the approval, security, memory-context and context-management layers.)

[OUTPUT]
- two_layer_context_middleware: AgentMiddleware applying cadence-governed base context tail blocks.

[POS]
Runs after ephemeral_delta_middleware; mutates only the tail of the user's latest message. The turn number is the
count of the user's own messages, so a notice the runtime appends mid-run neither moves the block nor advances the
cadence. Layer 2 dialectic is disabled on the live path (no candidate_memories); use Lab/API for dialectic
experiments.
"""

from __future__ import annotations

import os
import re
from collections.abc import Awaitable, Callable, Sequence
from typing import cast

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, AnyMessage, BaseMessage, HumanMessage, SystemMessage

from myrm_agent_harness.agent.middlewares._session_context import get_session_notes_summary
from myrm_agent_harness.core.context_vars import chat_id_var
from myrm_agent_harness.core.message_origin import (
    count_user_authored_messages,
    is_user_authored_human_message,
    last_user_authored_index,
)
from myrm_agent_harness.core.message_tail import append_block_to_last_user_message
from myrm_agent_harness.toolkits.memory.two_layer_dialectic.injector import (
    TwoLayerContextInjector,
)
from myrm_agent_harness.toolkits.memory.two_layer_dialectic.models import (
    DialecticCadenceConfig,
)

_DEFAULT_CONTEXT_CADENCE = 5
_MAX_DIGEST_CHARS = 1200
_LIVE_ENV = "MYRM_TWO_LAYER_CONTEXT_LIVE"
_BASE_CONTEXT_PATTERN = re.compile(r"<base_context[\s\S]*?</base_context>", re.IGNORECASE)
_DIALECTIC_PATTERN = re.compile(r"<dialectic_reconciliation[\s\S]*?</dialectic_reconciliation>", re.IGNORECASE)

_injector = TwoLayerContextInjector(
    config=DialecticCadenceConfig(
        context_cadence=_DEFAULT_CONTEXT_CADENCE,
        dialectic_cadence=1_000_000,
    )
)


def _live_enabled() -> bool:
    return os.getenv(_LIVE_ENV, "1").strip().lower() not in ("0", "false", "no", "off")


def _message_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        return "\n".join(parts)
    return ""


def _build_session_digest(messages: Sequence[BaseMessage]) -> str:
    """Compact rolling synopsis from recent dialogue (no extra LLM call)."""
    snippets: list[str] = []
    for msg in reversed(messages):
        if len(snippets) >= 6:
            break
        if is_user_authored_human_message(msg) or isinstance(msg, AIMessage):
            text = _message_text(msg.content)
            if not text:
                continue
            role = "Assistant" if isinstance(msg, AIMessage) else "User"
            line = f"{role}: {text[:280]}"
            snippets.append(line)
    if not snippets:
        return "Session just started; no prior turns."
    digest = "\n".join(reversed(snippets))
    if len(digest) > _MAX_DIGEST_CHARS:
        return digest[: _MAX_DIGEST_CHARS - 3] + "..."
    return digest


def _peer_cards_from_state(state: object) -> list[str]:
    if not isinstance(state, dict):
        return []
    raw = state.get("two_layer_peer_cards")
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    summary = state.get("two_layer_peer_card_summary")
    if isinstance(summary, str) and summary.strip():
        return [summary.strip()]
    return []


def _session_summary_from_state(state: object, fallback: str) -> str:
    if isinstance(state, dict):
        override = state.get("two_layer_session_summary")
        if isinstance(override, str) and override.strip():
            return override.strip()
    return fallback


def _strip_prior_tail_blocks(text: str) -> str:
    """Remove prior base_context / dialectic blocks before re-appending (same-turn idempotency)."""
    stripped = _BASE_CONTEXT_PATTERN.sub("", text)
    stripped = _DIALECTIC_PATTERN.sub("", stripped)
    return stripped.rstrip()


def _append_text_to_last_user_message(
    messages: Sequence[AnyMessage],
    appendix: str,
) -> list[AnyMessage] | None:
    if not appendix.strip():
        return None

    target_idx = last_user_authored_index(messages)
    if target_idx == -1:
        return None

    out = list(messages)
    original = cast(HumanMessage, out[target_idx])
    if isinstance(original.content, str):
        out[target_idx] = HumanMessage(
            content=_strip_prior_tail_blocks(original.content.rstrip()),
            additional_kwargs=dict(original.additional_kwargs),
            id=original.id,
            name=original.name,
        )
    return append_block_to_last_user_message(out, appendix)


class TwoLayerContextMiddleware(AgentMiddleware):
    name = "two_layer_context_middleware"

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        if not _live_enabled():
            return await handler(request)

        session_id = (chat_id_var.get() or "").strip()
        if not session_id or session_id == "default":
            return await handler(request)

        turn = count_user_authored_messages(request.messages)
        if turn < 1:
            return await handler(request)

        digest = _build_session_digest(request.messages)
        state = getattr(request, "state", None)
        notes_summary = get_session_notes_summary()
        if notes_summary and notes_summary.strip():
            session_summary = notes_summary.strip()
        else:
            session_summary = _session_summary_from_state(state, digest)
        peer_cards = _peer_cards_from_state(state)

        injection = _injector.assemble_injection(
            session_id=session_id,
            turn=turn,
            session_summary=session_summary,
            peer_cards=peer_cards or None,
            candidate_memories=[],
            force_refresh_base=False,
            force_dialectic=False,
        )

        blocks: list[str] = []
        if injection.layer1_base_context.strip():
            blocks.append(injection.layer1_base_context.strip())
        if injection.layer2_dialectic_block.strip():
            blocks.append(injection.layer2_dialectic_block.strip())
        if not blocks:
            return await handler(request)

        appendix = "\n\n".join(blocks)
        updated = _append_text_to_last_user_message(request.messages, appendix)
        if updated is None:
            return await handler(request)

        # Prefix invariant: SystemMessage bytes must remain untouched.
        for before, after in zip(request.messages, updated, strict=False):
            if (
                isinstance(before, SystemMessage)
                and isinstance(after, SystemMessage)
                and before.content != after.content
            ):
                return await handler(request)

        return await handler(request.override(messages=updated))


two_layer_context_middleware = TwoLayerContextMiddleware()
