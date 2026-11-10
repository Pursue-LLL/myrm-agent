"""Token estimate of a message that replays signed reasoning: the reasoning is in the prompt, the signature tag is not."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from myrm_agent_harness.core.thinking_blocks import THINKING_BLOCKS_KEY
from myrm_agent_harness.utils.text_utils import get_token_count
from myrm_agent_harness.utils.token_estimation import estimate_message_tokens, estimate_messages_tokens

_REASONING = "Compare the two caches before deciding which prefix to keep."
_SIGNED = {"type": "thinking", "thinking": _REASONING, "signature": "sig-1"}
_REDACTED = {"type": "redacted_thinking", "data": "opaque-reasoning-data"}


def _answer(*blocks: dict[str, str]) -> AIMessage:
    extras = {THINKING_BLOCKS_KEY: list(blocks)} if blocks else {}
    return AIMessage(content="ok", additional_kwargs=extras)


def test_the_reasoning_a_message_replays_counts_as_prompt() -> None:
    bare = estimate_message_tokens(_answer())
    replaying = estimate_message_tokens(_answer(_SIGNED, _REDACTED))

    assert replaying - bare == get_token_count(_REASONING + "opaque-reasoning-data")


def test_the_signature_is_not_counted() -> None:
    short = {**_SIGNED, "signature": "s"}
    long = {**_SIGNED, "signature": "s" * 4000}

    assert estimate_message_tokens(_answer(short)) == estimate_message_tokens(_answer(long))


def test_a_block_the_provider_would_refuse_is_not_counted() -> None:
    unsigned = {"type": "thinking", "thinking": _REASONING}

    assert estimate_message_tokens(_answer(unsigned)) == estimate_message_tokens(_answer())


def test_only_an_assistant_message_replays_reasoning() -> None:
    human = HumanMessage(content="ok", additional_kwargs={THINKING_BLOCKS_KEY: [_SIGNED]})

    assert estimate_message_tokens(human) == estimate_message_tokens(HumanMessage(content="ok"))


def test_a_conversation_total_includes_the_reasoning_of_its_loop() -> None:
    history = [_answer(_SIGNED), _answer(_SIGNED)]

    assert estimate_messages_tokens(history) == 2 * estimate_message_tokens(_answer(_SIGNED))
    assert estimate_messages_tokens(history) > estimate_messages_tokens([_answer(), _answer()])
