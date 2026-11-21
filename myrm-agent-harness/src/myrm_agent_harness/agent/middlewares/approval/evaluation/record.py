"""What the approval stage decided for one model response, in the form the graph state keeps it.

[INPUT]
- langchain.agents.middleware.types::AgentState, OmitFromSchema (POS: The agent state a middleware extends, and the marker that keeps a key out of the graph's input and output.)
- langchain_core.messages::ToolCall (POS: LangGraph message types)

[OUTPUT]
- APPROVAL_EVALUATION_KEY: the graph-state key that holds the evaluation
- ApprovalEvaluation, PendingCall, RefusedCall: the evaluation of one model response
- PATH_PINS_KEY, PathPin: the graph-state key that holds the files each file call was judged on, and one such record
- ApprovalEvaluationState: the state schema the evaluation node adds to the agent graph
- build_evaluation, evaluation_matches, pending_calls, refused_calls: build one, check it belongs to a message, read it back as the tuples the batch processor uses

[POS]
An approval card is answered by resuming the node that asked for it, and LangGraph resumes a node by running it again
from its first line. The verdicts therefore cannot be reached inside that node: they are made by an earlier node and
kept here, in a checkpointed state key, so the resumed node reads them back instead of judging the batch a second time.
The files each file call was judged on are kept the same way, for the tool-call hook that runs the call.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, NotRequired, TypedDict

from langchain.agents.middleware.types import AgentState, OmitFromSchema
from langchain_core.messages import ToolCall

APPROVAL_EVALUATION_KEY = "approval_evaluation"
PATH_PINS_KEY = "approval_path_pins"
# A state key the graph keeps and checkpoints but leaves out of its input and output.
_PRIVATE_STATE = OmitFromSchema(input=True, output=True)


class RefusedCall(TypedDict):
    """A call the evaluation refused: its position in the model response and the text that answers it."""

    index: int
    tool_call: ToolCall
    content: str


class PendingCall(TypedDict):
    """A call that waits for a person: its position, permission type, the reason to ask, and the card's extras."""

    index: int
    tool_call: ToolCall
    permission_type: str
    reason: str
    context: dict[str, object] | None


class ApprovalEvaluation(TypedDict):
    """The verdicts for the calls of one model response. ``message_id`` names that response."""

    message_id: str | None
    refused: list[RefusedCall]
    pending: list[PendingCall]


class PathPin(TypedDict):
    """The files a file call was judged on: the paths as the call typed them, and the files those paths opened.

    ``opened`` holds ``""`` for a text no file can be named by.
    """

    typed: list[str]
    opened: list[str]


class ApprovalEvaluationState(AgentState[object]):
    """The agent state plus the evaluation of the latest model response and the pins of its file calls, by call id.

    Private: not part of the graph's input or output.
    """

    approval_evaluation: NotRequired[Annotated[ApprovalEvaluation | None, _PRIVATE_STATE]]
    approval_path_pins: NotRequired[Annotated[dict[str, PathPin] | None, _PRIVATE_STATE]]


def build_evaluation(
    message_id: str | None,
    refused: Sequence[tuple[int, ToolCall, str]],
    pending: Sequence[tuple[int, ToolCall, str, str, dict[str, object] | None]],
) -> ApprovalEvaluation:
    """The batch processor's verdict tuples as the plain structure the checkpoint stores."""
    return ApprovalEvaluation(
        message_id=message_id,
        refused=[RefusedCall(index=index, tool_call=call, content=content) for index, call, content in refused],
        pending=[
            PendingCall(index=index, tool_call=call, permission_type=permission_type, reason=reason, context=context)
            for index, call, permission_type, reason, context in pending
        ],
    )


def evaluation_matches(evaluation: ApprovalEvaluation | None, message_id: str | None) -> bool:
    """Whether *evaluation* was made for the model response *message_id*; a response without an id matches nothing."""
    return evaluation is not None and message_id is not None and evaluation["message_id"] == message_id


def refused_calls(evaluation: ApprovalEvaluation) -> list[tuple[int, ToolCall, str]]:
    """The refused calls as ``(index, call, content)``, the shape the batch processor returns them in."""
    return [(entry["index"], entry["tool_call"], entry["content"]) for entry in evaluation["refused"]]


def pending_calls(evaluation: ApprovalEvaluation) -> list[tuple[int, ToolCall, str, str, dict[str, object] | None]]:
    """The calls that wait for a person as ``(index, call, permission_type, reason, context)``."""
    return [
        (entry["index"], entry["tool_call"], entry["permission_type"], entry["reason"], entry["context"])
        for entry in evaluation["pending"]
    ]
