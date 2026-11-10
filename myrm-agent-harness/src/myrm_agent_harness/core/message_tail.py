"""Placing a block on the tail of the user's own message.

[INPUT]
- core.message_origin::last_user_authored_index (POS: Message-provenance primitives shared by the approval, security, memory-context and context-management layers.)
- Third-party: langchain_core

[OUTPUT]
- append_block_to_last_user_message: Returns the messages with a text block appended to the user's latest message; the history before it stays byte-identical.

[POS]
Tail-of-turn injection primitive: per-turn content lives only on the user's latest message so the SystemMessage and
earlier history keep their prompt-cache prefix. Shared by the memory tail injectors and by the focus notices of the
agent loop, so it lives in ``core`` beside the provenance primitives it is built on.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import cast

from langchain_core.messages import AnyMessage, HumanMessage

from myrm_agent_harness.core.message_origin import last_user_authored_index

logger = logging.getLogger(__name__)


def append_block_to_last_user_message(messages: Sequence[AnyMessage], block: str) -> list[AnyMessage]:
    """Return ``messages`` with ``block`` appended to the tail of the user's latest message.

    That is the latest message the user wrote, not a notice the runtime appended behind it: such a notice is added
    and dropped between requests of one run, and a block that followed it would move with it and change the request
    prefix the provider caches. The input sequence and its messages are never mutated. Multimodal content keeps
    every original part untouched and gains one trailing text part. Without a block or a user message the result is
    an unmodified copy.
    """
    out_messages = list(messages)
    if not block:
        return out_messages

    target_idx = last_user_authored_index(out_messages)
    if target_idx == -1:
        logger.debug("No user message found in request messages; skipping tail injection")
        return out_messages

    original_human = cast(HumanMessage, out_messages[target_idx])
    content = original_human.content
    new_content: str | list[str | dict[str, object]]
    if isinstance(content, str):
        new_content = f"{content}\n\n{block}" if content else block
    else:
        new_content = [*content, {"type": "text", "text": f"\n\n{block}"}]
    out_messages[target_idx] = HumanMessage(
        content=new_content,
        additional_kwargs=dict(original_human.additional_kwargs),
        id=original_human.id,
        name=original_human.name,
    )
    return out_messages
