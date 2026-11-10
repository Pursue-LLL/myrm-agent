"""Resume addressing — binds an answer to the pause it was given for

[INPUT]
- agent.streaming.interrupt_events::INTERRUPT_ID_KEY (POS: 流事件与 resume 载荷共用的卡片 id 键)

[OUTPUT]
- address_resume: pure rule that turns a resume command into one LangGraph resolves per interrupt id
- address_resume_to_pending: reads the thread's pending interrupts and applies ``address_resume``

[POS]
LangGraph answers whichever interrupt is pending when a resume carries no id, and refuses an unaddressed resume
while several interrupts are pending. Both hurt a chat whose parallel tool calls each ask for approval. It also hands an
answer keyed by an interrupt id that is no longer pending to the next pause of that task, so an old card could answer a
later one.

Every pause has its own interrupt id, each pause of a task that pauses several times in a row included, and the stream
event of the pause carries that id as its card id (``interruptId``, see ``streaming/interrupt_events.py``). The client
echoes the card id it arrived with. It is honoured only while that interrupt is pending: then the command becomes
``Command(resume={interrupt_id: answer})``. Any other id (settled, not reached yet, or not an interrupt id at all) is
rewritten to an interrupt id that nothing has, which LangGraph ignores: the answer is delivered to nobody and the run
pauses again at what is really pending, instead of the answer being mistaken for the reply to another pause.

A resume without an id is left untouched while at most one interrupt is pending, so every existing caller (IM
replies, voice, timers) behaves exactly as before. With several pending, only a global rejection (the timeout timer's
``{"decision": "reject"}``) is broadcast to all of them: refusing is safe to repeat, approving is never applied to an
interrupt the user did not individually answer. Any other unaddressed answer reaches LangGraph unchanged and is refused
there.
"""

from __future__ import annotations

from collections.abc import Collection

from langchain_core.runnables.config import RunnableConfig
from langgraph.types import Command

from myrm_agent_harness.agent.streaming.interrupt_events import INTERRUPT_ID_KEY
from myrm_agent_harness.utils.logger_utils import get_agent_logger

logger = get_agent_logger(__name__)

# Well-formed, so LangGraph reads the resume as an id map; held by no interrupt, so LangGraph ignores it.
_NO_INTERRUPT_ID = "0" * 32


def address_resume(command: Command[object], pending: Collection[str]) -> Command[object]:
    """``command`` rewritten so that LangGraph resolves it per interrupt id; ``pending`` holds every pending id."""
    answer = command.resume
    resume: object
    if isinstance(answer, dict) and isinstance(answer.get(INTERRUPT_ID_KEY), str):
        card_id = answer[INTERRUPT_ID_KEY]
        content = {key: value for key, value in answer.items() if key != INTERRUPT_ID_KEY}
        if card_id in pending:
            resume = {card_id: content}
        else:
            logger.warning(
                "Ignoring an answer addressed to %.80r: that pause is not pending (pending=%s)", card_id, list(pending)
            )
            resume = {_NO_INTERRUPT_ID: content}
    elif len(pending) > 1 and _is_global_rejection(answer):
        logger.warning("Rejecting all %d pending interrupts with one global rejection", len(pending))
        resume = dict.fromkeys(pending, answer)
    else:
        resume = answer
    return Command(graph=command.graph, update=command.update, resume=resume, goto=command.goto)


async def address_resume_to_pending(
    agent_graph: object | None,
    command: Command[object],
    thread_id: str,
) -> Command[object]:
    """``address_resume`` against the interrupts pending on ``thread_id``; unchanged when the thread cannot be read."""
    pending = await _pending_ids(agent_graph, thread_id)
    return command if pending is None else address_resume(command, pending)


async def _pending_ids(agent_graph: object | None, thread_id: str) -> frozenset[str] | None:
    """Ids of the interrupts ``thread_id`` is paused on; ``None`` when the thread cannot be read."""
    aget_state = getattr(agent_graph, "aget_state", None)
    if aget_state is None:
        return None
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
    try:
        snapshot = await aget_state(config)
    except (AttributeError, KeyError, LookupError, OSError, RuntimeError, TypeError, ValueError) as exc:
        logger.warning("Failed to read pending interrupts before resume (thread=%s): %s", thread_id, exc)
        return None
    interrupts = getattr(snapshot, "interrupts", ()) or ()
    return frozenset(
        interrupt_id for interrupt in interrupts if isinstance(interrupt_id := getattr(interrupt, "id", None), str)
    )


def _is_global_rejection(answer: object) -> bool:
    """The one-decision answer shape (``decision`` without ``decisions``) carrying a rejection."""
    return isinstance(answer, dict) and answer.get("decision") == "reject" and "decisions" not in answer
