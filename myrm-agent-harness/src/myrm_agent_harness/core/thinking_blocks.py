"""Signed reasoning blocks: the reasoning an Anthropic-family answer hands back so the next request can return it.

A ``thinking`` block carries the reasoning text and a signature that binds it to the conversation that produced it;
a ``redacted_thinking`` block carries the same reasoning as opaque data. The provider checks them on every request, so
they are kept exactly as received, in order, on the AIMessage they arrived with, and replayed only on a request that
continues that conversation.

[INPUT]
- langchain_core.messages::AIMessage, BaseMessage (POS: the message the blocks ride on)

[OUTPUT]
- THINKING_BLOCKS_KEY: the ``additional_kwargs`` key, and the wire-message key, the blocks travel under
- ThinkingBlock, RedactedThinkingBlock, SignedThinkingBlock: the two block shapes
- coerce_thinking_blocks: the replayable blocks of a raw ``thinking_blocks`` value, validated and copied
- carried_thinking_blocks: the same blocks, or none while ``MYRM_THINKING_BLOCK_REPLAY`` switches replay off
- ThinkingBlockAssembler: builds the blocks of one stream from their deltas, one draft per provider content index
- thinking_blocks_text: the reasoning text a message's blocks put in the prompt, for token estimation
- without_thinking_blocks: messages with the blocks removed, for a call whose prompt is not the conversation's

[POS]
Shared by the transports (capture and replay on the Anthropic and Bedrock wires), the chat-model adapter (state
capture), the context pipeline (turn-scoped pruning) and the token estimator. It lives in ``core`` so ``toolkits/`` and
``agent/`` agree on one block shape without depending on each other.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage

THINKING_BLOCKS_KEY: Final = "thinking_blocks"

# Operations switch: with replay off no block enters conversation state or a request, so a tool loop runs without
# reasoning, exactly as a model that returns no signed blocks does.
_REPLAY_SWITCH_ENV: Final = "MYRM_THINKING_BLOCK_REPLAY"
_OFF_VALUES: Final = frozenset({"0", "false", "no", "off"})


class ThinkingBlock(TypedDict):
    """Reasoning text and the signature that binds it to the conversation that produced it."""

    type: Literal["thinking"]
    thinking: str
    signature: str


class RedactedThinkingBlock(TypedDict):
    """Reasoning the provider withheld; the opaque data is all that can be handed back."""

    type: Literal["redacted_thinking"]
    data: str


SignedThinkingBlock = ThinkingBlock | RedactedThinkingBlock


def _coerce_block(raw: Mapping[str, object]) -> SignedThinkingBlock | None:
    """A copy of ``raw`` in block shape, or None when the provider would not take it back (no signature, no data)."""
    kind = raw.get("type")
    if kind == "thinking":
        signature = raw.get("signature")
        if isinstance(signature, str) and signature:
            # An empty text with a signature is a block: ``display: omitted`` answers carry exactly that.
            text = raw.get("thinking")
            return {"type": "thinking", "thinking": text if isinstance(text, str) else "", "signature": signature}
    elif kind == "redacted_thinking":
        data = raw.get("data")
        if isinstance(data, str) and data:
            return {"type": "redacted_thinking", "data": data}
    return None


def coerce_thinking_blocks(raw: object) -> list[SignedThinkingBlock]:
    """The replayable blocks of a ``thinking_blocks`` value, in order; anything the provider would refuse is dropped."""
    if not isinstance(raw, list):
        return []
    return [block for item in raw if isinstance(item, Mapping) and (block := _coerce_block(item)) is not None]


def carried_thinking_blocks(raw: object) -> list[SignedThinkingBlock]:
    """The blocks that may enter conversation state or leave in a request; none while the replay switch is off.

    The switch is read on every call, so flipping it takes effect on the next request without a restart.
    """
    if os.environ.get(_REPLAY_SWITCH_ENV, "1").strip().lower() in _OFF_VALUES:
        return []
    return coerce_thinking_blocks(raw)


@dataclass(slots=True)
class _Draft:
    """A block in the making: ``redacted_data`` is set for a redacted block, which arrives whole."""

    redacted_data: str | None = None
    text: list[str] = field(default_factory=list)
    signature: list[str] = field(default_factory=list)


class ThinkingBlockAssembler:
    """Builds the signed reasoning blocks of one stream from their deltas.

    Text and signature of a block arrive in pieces under the provider's content index, and a draft starts with its
    first piece because not every provider announces a reasoning block. A block is complete when the provider closes
    that index, never earlier, so a stream cut short yields no half-signed block.
    """

    __slots__ = ("_drafts",)

    def __init__(self) -> None:
        self._drafts: dict[int, _Draft] = {}

    def _draft(self, index: int) -> _Draft:
        return self._drafts.setdefault(index, _Draft())

    def add_text(self, index: int, text: str) -> None:
        self._draft(index).text.append(text)

    def add_signature(self, index: int, signature: str) -> None:
        self._draft(index).signature.append(signature)

    def set_redacted(self, index: int, data: str) -> None:
        self._drafts[index] = _Draft(redacted_data=data)

    def close(self, index: int) -> SignedThinkingBlock | None:
        """The finished block at ``index``; None for an index that held no reasoning or ended unsigned."""
        draft = self._drafts.pop(index, None)
        if draft is None:
            return None
        if draft.redacted_data is not None:
            return _coerce_block({"type": "redacted_thinking", "data": draft.redacted_data})
        return _coerce_block(
            {"type": "thinking", "thinking": "".join(draft.text), "signature": "".join(draft.signature)}
        )


def thinking_blocks_text(message: BaseMessage) -> str:
    """The reasoning a message's blocks put in the prompt: thinking text and redacted data, not the signature tag."""
    if not isinstance(message, AIMessage):
        return ""
    blocks = coerce_thinking_blocks(message.additional_kwargs.get(THINKING_BLOCKS_KEY))
    return "".join(block["data"] if block["type"] == "redacted_thinking" else block["thinking"] for block in blocks)


def _without_blocks[M: BaseMessage](message: M) -> M:
    if isinstance(message, AIMessage) and THINKING_BLOCKS_KEY in message.additional_kwargs:
        kwargs = {key: value for key, value in message.additional_kwargs.items() if key != THINKING_BLOCKS_KEY}
        return message.model_copy(update={"additional_kwargs": kwargs})
    return message


def without_thinking_blocks[M: BaseMessage](messages: Sequence[M]) -> list[M]:
    """The messages without their signed reasoning blocks, the originals untouched.

    A block is bound to the exact prompt it was produced in, so a call that sends the conversation under another
    system prompt or tool set must not replay it.
    """
    return [_without_blocks(message) for message in messages]
