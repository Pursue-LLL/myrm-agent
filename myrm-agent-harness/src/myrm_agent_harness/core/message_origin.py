"""Who wrote a message: the user, or the runtime acting on the user's behalf.

The runtime appends HumanMessages behind the user's (file-restore and sub-agent notices, recovery hints, request-local
notices) and marks them ``is_system_synthetic``. Everything that acts on what the user said, or that treats the user's
message as the start of a turn, must skip those.

It also appends SystemMessage blocks for the acting model alone (the data-boundary rules, the canary, the session
directories) and marks them the same way, so a model that only advises is never shown them.

[INPUT]
- langchain_core.messages::BaseMessage, HumanMessage, SystemMessage

[OUTPUT]
- is_user_authored_human_message: True for a HumanMessage the user wrote, False for runtime-injected ones and other
  message types
- runtime_human_message: a HumanMessage the runtime writes on the user's behalf, marked so the predicate skips it
- runtime_system_message: a SystemMessage block the runtime writes for the acting model, marked as the runtime's
- is_runtime_system_block: True for a SystemMessage built by ``runtime_system_message``
- last_user_authored_index: index of the user's latest message, the start of the current turn (-1 when there is none)
- count_user_authored_messages: how many messages the user wrote, i.e. the turn number

[POS]
Message-provenance primitives shared by the approval, security, memory-context and context-management layers, by the
advisor fan-out and by the tail-of-turn injectors in ``toolkits/``, and the constructors of the messages they skip. It
lives in ``core`` so the toolkits can place a block on the user's own message without depending on ``agent/``.
"""

from __future__ import annotations

from collections.abc import Sequence

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

_SYNTHETIC_KEY = "is_system_synthetic"


def is_user_authored_human_message(msg: BaseMessage) -> bool:
    """Determine whether a message represents authentic user input rather than synthetic runtime injection."""
    if not isinstance(msg, HumanMessage):
        return False

    kwargs = getattr(msg, "additional_kwargs", {})
    if not isinstance(kwargs, dict):
        return True

    # Explicit synthetic flag
    if kwargs.get(_SYNTHETIC_KEY) is True:
        return False

    return kwargs.get("source") not in ("runtime", "system")


def runtime_human_message(content: str) -> HumanMessage:
    """A HumanMessage the runtime appends on the user's behalf; ``is_user_authored_human_message`` skips it."""
    return HumanMessage(content=content, additional_kwargs={_SYNTHETIC_KEY: True})


def runtime_system_message(content: str) -> SystemMessage:
    """A SystemMessage block the runtime appends for the acting model; ``is_runtime_system_block`` recognises it."""
    return SystemMessage(content=content, additional_kwargs={_SYNTHETIC_KEY: True})


def is_runtime_system_block(msg: BaseMessage) -> bool:
    """Whether a message is a system block the runtime appended for the acting model."""
    if not isinstance(msg, SystemMessage):
        return False
    kwargs = msg.additional_kwargs
    # A message rebuilt without validation can lose its kwargs; with no marker to read it is not the runtime's.
    return isinstance(kwargs, dict) and kwargs.get(_SYNTHETIC_KEY) is True


def last_user_authored_index(messages: Sequence[BaseMessage]) -> int:
    """Index of the latest message the user wrote, or -1 when the user wrote none."""
    return next((i for i in range(len(messages) - 1, -1, -1) if is_user_authored_human_message(messages[i])), -1)


def count_user_authored_messages(messages: Sequence[BaseMessage]) -> int:
    """How many messages the user wrote, which is the number of the turn the last of them opens."""
    return sum(1 for m in messages if is_user_authored_human_message(m))
