"""Request-local notices that keep their place and their text for the whole run.

A notice a middleware shows the model without storing it (the todo snapshot, an environment constraint) is rebuilt for
every model call. The provider caches the request prefix, and a reasoning block it returned is valid only for the
prefix it was written under, so within one run every request has to extend the one before it. A notice therefore
either stays the same on every request, or is written once and placed behind the message that was last at that moment.

[INPUT]
- langchain.agents.middleware::ModelRequest (POS: the request a model-call wrapper rewrites)
- core.message_origin::runtime_human_message (POS: marks a notice as written by the runtime, not by the user)

[OUTPUT]
- run_scope: the per-run dict a request carries, or None when it carries none
- frozen_for_run: renders a notice on the run's first request and hands back that one rendering on every later request
- last_stored_message: the newest message of a request that a notice can stand behind and keep its place
- NoticeLedger: append-only notices of one run, each placed behind the message that was last when it was written

[POS]
Shared by the middlewares whose notices change while a run goes on (todo focus, circuit-breaker constraints, the
advisor block, the completion guard's instruction). The run dict is the LangGraph run context, which is new for every
run, so nothing here outlives the run it was written in.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import cast

from langchain.agents.middleware import ModelRequest
from langchain_core.messages import AnyMessage, BaseMessage

from myrm_agent_harness.core.message_origin import runtime_human_message


def run_scope(request: ModelRequest) -> dict[str, object] | None:
    """The mutable per-run dict of ``request`` (the run context), or None when the request carries none."""
    context = getattr(request.runtime, "context", None) if request.runtime is not None else None
    return context if isinstance(context, dict) else None


async def frozen_for_run(
    scope: dict[str, object] | None,
    key: str,
    render: Callable[[], Awaitable[str | None]],
) -> str | None:
    """The notice of the run: ``render`` runs on the first request and its result is returned on every later one.

    A notice that is absent on the first request stays absent (``None`` is remembered too): a todo list the model
    starts in the middle of a run does not appear in the user's message halfway through. Without a run dict nothing
    can be remembered, so the notice is rendered each time.
    """
    if scope is None:
        return await render()
    if key in scope:
        frozen = scope[key]
        return frozen if isinstance(frozen, str) else None
    rendered = await render()
    scope[key] = rendered
    return rendered


def last_stored_message(messages: Sequence[BaseMessage]) -> BaseMessage | None:
    """The newest message of ``messages`` that carries an id, which only a message the graph stored does.

    A request-local notice has no id to be found by, so a notice cannot stand behind it and keep its place.
    """
    return next((message for message in reversed(messages) if message.id), None)


class NoticeLedger:
    """The notices of one run in the order they were written.

    A notice sits right behind the message that was last when it was written, on that request and on every later one,
    so no request changes a byte of the one before it. An anchor that is no longer in the request (or never had an id)
    leaves its notice at the end, which is where it would stand without a ledger.
    """

    def __init__(self, entries: list[list[str]]) -> None:
        # ``[anchor message id, text]`` pairs: plain lists of strings, so they can live in the run context.
        self._entries = entries

    @classmethod
    def of(cls, scope: dict[str, object] | None, key: str) -> NoticeLedger:
        """The ledger stored under ``key`` in the run dict; a fresh one when there is no run dict to keep it in."""
        stored = scope.get(key) if scope is not None else None
        if not isinstance(stored, list):
            stored = []
            if scope is not None:
                scope[key] = stored
        return cls(cast("list[list[str]]", stored))

    def latest_text(self) -> str | None:
        """The text of the newest notice, or None when nothing was written yet."""
        return self._entries[-1][1] if self._entries else None

    def record(self, anchor: BaseMessage | None, text: str) -> None:
        """Write a notice that stands behind ``anchor`` from now on, unless the newest notice already is that one."""
        entry = [(anchor.id if anchor is not None else None) or "", text]
        if not self._entries or self._entries[-1] != entry:
            self._entries.append(entry)

    def placed_in(self, messages: Sequence[AnyMessage]) -> list[AnyMessage]:
        """``messages`` with every notice of the ledger behind its anchor, as runtime-written HumanMessages."""
        if not self._entries:
            return list(messages)
        present = {m.id for m in messages if m.id}
        behind: dict[str, list[str]] = {}
        at_end: list[str] = []
        for anchor_id, text in self._entries:
            if anchor_id in present:
                behind.setdefault(anchor_id, []).append(text)
            else:
                at_end.append(text)
        placed: list[AnyMessage] = []
        for message in messages:
            placed.append(message)
            placed.extend(runtime_human_message(text) for text in behind.get(message.id or "", ()))
        placed.extend(runtime_human_message(text) for text in at_end)
        return placed
