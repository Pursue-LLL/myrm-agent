"""Cross-layer context variables shared by both agent/ and toolkits/.

ContextVars defined here can be safely imported from any layer without
introducing forbidden dependencies (e.g. toolkits/ → agent/).

[INPUT]
- (none at runtime — stdlib ContextVar definitions; core.security.types::AccessRoot only for typing)

[OUTPUT]
- user_timezone_var: User timezone string (e.g. "Asia/Shanghai")
- datetime_injection_enabled_var: Whether to inject timestamps into messages
- prompt_routing_key_var: Session-scoped routing key for OpenAI prompt cache affinity
- workspace_root_var: Sandbox workspace root for toolkit spill paths
- chat_id_var: Active chat/session id for per-session spill directories
- approval_session_var: Approval-routing session key shared by agent/ and toolkits/
- protected_paths_var: Goal-scoped protected path patterns every write channel must honour
- session_access_roots_var: The session grants as the host seeds them before a run starts
- AccessGrants / access_grants_var / open_access_grants: Every directory this run may reach beyond the workspace
  (declared, remembered for the session, approved for one call), mutable across graph nodes
- standing_access_roots / reachable_access_roots: The ones that outlast a call, and all of them right now
- current_tool_call_id_var: The call the tool body is running inside (set by the tool-call middleware)
- approval_notes_var: The human's notes on this run's approvals, keyed by tool call id
- publish_approval_notes / stash_approval_note / claim_approval_note: the note hand-off
- scoped_value: Bind a ContextVar for a ``with`` block and restore what it held on exit

[POS]
Foundation ContextVar registry. Eliminates coupling between agent/ and toolkits/
by providing a neutral location for runtime context that both layers need.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.core.security.types import AccessRoot

user_timezone_var: ContextVar[str | None] = ContextVar("user_timezone", default=None)
datetime_injection_enabled_var: ContextVar[bool] = ContextVar("datetime_injection_enabled", default=True)

# OpenAI prompt_cache_key routing hint — set per-session to maximize KV cache hit
# rate by ensuring requests from the same session route to the same inference node.
prompt_routing_key_var: ContextVar[str | None] = ContextVar("prompt_routing_key", default=None)

workspace_root_var: ContextVar[str] = ContextVar("workspace_root", default="")
chat_id_var: ContextVar[str] = ContextVar("chat_id", default="")

# Approval-routing session key. Held here rather than in
# agent/middlewares/_session_context so the sandbox executor can resolve the
# active approval session without depending on agent/; the agent accessor
# keeps ``get_approval_session`` / ``set_approval_session`` for its callers.
approval_session_var: ContextVar[str] = ContextVar("approval_session_key", default="")

# Goal-scoped protected path patterns. Held here rather than in
# agent/middlewares/_session_context so the sandbox executor can enforce the same
# rules as the file tools and the shell pre-flight without depending on agent/.
protected_paths_var: ContextVar[tuple[str, ...]] = ContextVar("protected_paths", default=())

# The session grants a host seeds before a run starts, resolved and validated when granted
# (agent/security/session_access.py owns them). Once the run opens its ``AccessGrants`` they live there.
session_access_roots_var: ContextVar[tuple[AccessRoot, ...]] = ContextVar("session_access_roots", default=())


@dataclass(slots=True)
class AccessGrants:
    """The directories one run may reach beyond its workspace, by how long the person's say-so lasts.

    ``declared`` is what the policy names, fixed for the run; ``session`` is what the person asked to remember;
    ``once`` is what the approval of a single call opened, dropped at the next model response.
    """

    declared: tuple[AccessRoot, ...] = ()
    session: tuple[AccessRoot, ...] = ()
    once: tuple[AccessRoot, ...] = ()


# One mutable object per run, because LangGraph runs each node in a copy of the context: a grant rebound
# in the approval node would never reach the tool node, a grant written into this object does. Held here so
# the sandbox executor reaches the same directories the permission engine judged by, without depending on agent/.
access_grants_var: ContextVar[AccessGrants | None] = ContextVar("access_grants", default=None)


def open_access_grants(declared: tuple[AccessRoot, ...]) -> AccessGrants:
    """Open this run's grants, keeping the session grants the host seeded. Called once per run, before the graph streams."""
    held = access_grants_var.get()
    session = held.session if held is not None else session_access_roots_var.get()
    grants = AccessGrants(declared=declared, session=session)
    access_grants_var.set(grants)
    return grants


def standing_access_roots() -> tuple[AccessRoot, ...]:
    """The directories that outlast a single call: what the policy declares and what the session granted."""
    grants = access_grants_var.get()
    if grants is None:
        return session_access_roots_var.get()
    return (*grants.declared, *grants.session)


def reachable_access_roots() -> tuple[AccessRoot, ...]:
    """Every directory the run may reach beyond its workspace right now, a call's own approval included."""
    grants = access_grants_var.get()
    return (*standing_access_roots(), *(grants.once if grants is not None else ()))


# The tool call the running tool body belongs to. The tool-call middleware sets it around
# the dispatch so a gate can tell one call from another; tool bodies read it and never set it.
current_tool_call_id_var: ContextVar[str] = ContextVar("current_tool_call_id", default="")

# The human's notes on this run's approvals, keyed by tool call id. A gate the human answered
# stashes the note it read from the answer; the tool-call middleware claims it once the tool
# returned and appends it after the tool result. Held here so toolkits/ can stash without
# importing agent/, and as a mutable dict because LangGraph runs a tool body in a copied
# context: rebinding a ContextVar there would not be visible to the middleware, mutating the
# published dict is.
approval_notes_var: ContextVar[dict[str, str] | None] = ContextVar("approval_notes", default=None)


def publish_approval_notes() -> None:
    """Open this run's approval-note store. Called once per run, before the graph streams."""
    approval_notes_var.set({})


def stash_approval_note(note: str) -> None:
    """Record the human's note for the tool call currently running. A no-op without a note."""
    store = approval_notes_var.get()
    call_id = current_tool_call_id_var.get()
    if store is not None and call_id and note:
        store[call_id] = note


def claim_approval_note(call_id: str) -> str:
    """Take the note for ``call_id``, once; empty when the human left none."""
    store = approval_notes_var.get()
    if store is None:
        return ""
    return store.pop(call_id, "")


@contextmanager
def scoped_value[T](var: ContextVar[T], value: T) -> Iterator[T]:
    """Bind ``var`` to ``value`` for the ``with`` block, and restore what it held when the block ends."""
    token = var.set(value)
    try:
        yield value
    finally:
        var.reset(token)
