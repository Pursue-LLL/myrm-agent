"""Who wrote a HumanMessage: the user, or the runtime acting on the user's behalf.

The runtime appends HumanMessages behind the user's (file-restore and sub-agent notices, recovery hints) and marks
them ``is_system_synthetic``. Middlewares that act on what the user said must skip those.

[INPUT]
- langchain_core.messages::BaseMessage, HumanMessage

[OUTPUT]
- is_user_authored_human_message: True for a HumanMessage the user wrote, False for runtime-injected ones and other
  message types
- runtime_human_message: a HumanMessage the runtime writes on the user's behalf, marked so the predicate skips it

[POS]
Message-provenance predicate shared by the approval and security middlewares, and the constructor of the messages it skips.
"""

from __future__ import annotations

from langchain_core.messages import BaseMessage, HumanMessage


def is_user_authored_human_message(msg: BaseMessage) -> bool:
    """Determine whether a message represents authentic user input rather than synthetic runtime injection."""
    if not isinstance(msg, HumanMessage):
        return False

    kwargs = getattr(msg, "additional_kwargs", {})
    if not isinstance(kwargs, dict):
        return True

    # Explicit synthetic flag
    if kwargs.get("is_system_synthetic") is True:
        return False

    return kwargs.get("source") not in ("runtime", "system")


def runtime_human_message(content: str) -> HumanMessage:
    """A HumanMessage the runtime appends on the user's behalf; ``is_user_authored_human_message`` skips it."""
    return HumanMessage(content=content, additional_kwargs={"is_system_synthetic": True})
