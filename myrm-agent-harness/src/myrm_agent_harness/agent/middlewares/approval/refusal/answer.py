"""The result that answers a refused call, marked with who refused it.

[INPUT]
- .wording::DenialCause (POS: who or what refused the call)
- utils.errors::ToolErrorCategory (POS: the category a step shows and the fault side is attributed from)

[OUTPUT]
- refusal_answer: the error ToolMessage that answers a refused call
- is_refusal_answer: whether a message is such an answer, as opposed to a tool that ran and failed
- rejection_cause: who refused a call whose approval was settled with a rejection

[POS]
Every refusal the approval flow gives is built here, so each carries a category. Without one the stream
attributes the failure to the built-in tool, and a person who declined a command is told a tool failed.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeGuard

from langchain_core.messages import BaseMessage, ToolCall, ToolMessage

from myrm_agent_harness.utils.errors import ToolErrorCategory

from .wording import DenialCause

_CATEGORY_OF_CAUSE: Mapping[DenialCause, ToolErrorCategory] = {
    DenialCause.POLICY: ToolErrorCategory.POLICY_DENIED,
    DenialCause.USER: ToolErrorCategory.USER_DECLINED,
    DenialCause.TIMEOUT: ToolErrorCategory.APPROVAL_TIMEOUT,
}
_REFUSAL_CATEGORIES = frozenset(category.value for category in _CATEGORY_OF_CAUSE.values())


def refusal_answer(tool_call: ToolCall, content: str, cause: DenialCause) -> ToolMessage:
    """The error result that answers a refused call, so the model reads the refusal as the call's own result."""
    return ToolMessage(
        content=content,
        name=tool_call.get("name") or "unknown",
        tool_call_id=tool_call.get("id") or "",
        status="error",
        additional_kwargs={"error_category": _CATEGORY_OF_CAUSE[cause].value},
    )


def is_refusal_answer(message: BaseMessage) -> TypeGuard[ToolMessage]:
    """Whether *message* answers a call that was refused and never ran, not a call that ran and failed."""
    return isinstance(message, ToolMessage) and message.additional_kwargs.get("error_category") in _REFUSAL_CATEGORIES


def rejection_cause(decision: Mapping[str, object]) -> DenialCause:
    """Who refused: the approval timer settles a decision with ``timed_out``; any other rejection is a person's."""
    return DenialCause.TIMEOUT if decision.get("timed_out") else DenialCause.USER
