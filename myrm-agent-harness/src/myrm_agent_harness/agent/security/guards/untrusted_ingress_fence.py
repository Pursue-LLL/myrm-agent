"""Untrusted Ingress Fence — call-time tool denial for external inbound messages.

When an Agent session processes untrusted external input (e.g., messages from
external peers, webhook triggers, public bot mentions), this fence denies high-privilege
destructive tools (arbitrary execution, file mutation, persistent-memory mutation,
desktop control and screen capture, subagent escalation, cron backdoors, and
skill manipulation) at tool-call time. Tools outside these lists, MCP tools included, pass
the fence and stay under the regular approval pipeline.

Memory mutations are fenced independently of how a host scopes the
memory namespaces: a persisted instruction steers every later turn that reads that
namespace, and memory_manage_tool resolves ids across the whole bound namespace chain
(including shared contexts) and applies delete/update without a pending review.

[INPUT]
- Tool names of the calls the Agent runtime is about to run
- core.security.tool_registry.registry::resolve_permission_type (POS: the abstract permission type of a tool name)
- External ingress activation flag

[OUTPUT]
- is_untrusted_ingress_active(): ContextVar check
- set_untrusted_ingress() / reset_untrusted_ingress(): ContextVar mutators
- untrusted_ingress_scope(): Scoped mutator that marks everything run or spawned inside it, then restores the prior state
- is_tool_allowed_under_untrusted_ingress(): Single tool authorization check
- DISALLOWED_UNTRUSTED_TOOLS / DISALLOWED_UNTRUSTED_PERMISSIONS: the fenced tool names and the fenced permission types

[POS]
Layer 2 runtime security guard. Sits between Inbound Task Ingress and Agent Tool Registry.
Denies the listed tools at call time, so an injected instruction cannot run shell commands, write or edit
files, or rewrite the owner's long-term memory through them. The tools stay registered, and the fence
does not cover a tool outside the lists.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from myrm_agent_harness.core.security.tool_registry.registry import resolve_permission_type

logger = logging.getLogger(__name__)

# Tools strictly disallowed when handling untrusted external inputs.
# These tools possess destructive host privileges (arbitrary shell, file mutation) or mutate
# long-term memory (save a new entry, update/delete/correct an existing one). Every entry is the name of a
# tool: the check below runs without the call's arguments, so a permission type listed here would never match.
# ``bash_process_tool`` types into the stdin of a running shell, which runs commands as the bash tool does.
DISALLOWED_UNTRUSTED_TOOLS: frozenset[str] = frozenset(
    {
        "bash_code_execute_tool",
        "bash_process_tool",
        "file_write_tool",
        "file_edit_tool",
        "memory_save_tool",
        "memory_manage_tool",
    }
)

# High-risk abstract permission types strictly disallowed under untrusted ingress.
# Automatically blocks code execution, file mutation, desktop capture and control,
# subagent escalation, cron backdoors, and dynamic skill manipulation.
DISALLOWED_UNTRUSTED_PERMISSIONS: frozenset[str] = frozenset(
    {
        "code_interpreter",
        "file_write",
        "desktop_control",
        "desktop_capture",
        "spawn_subagent",
        "invoke_external_agent",
        "cron_manage",
        "skill_manage",
    }
)

_untrusted_ingress_var: ContextVar[bool] = ContextVar("untrusted_ingress_active", default=False)


def is_untrusted_ingress_active() -> bool:
    """Check if the current async execution context is marked as untrusted ingress."""
    return _untrusted_ingress_var.get()


def set_untrusted_ingress(active: bool = True) -> None:
    """Set the untrusted ingress status for the current async execution context."""
    _untrusted_ingress_var.set(active)
    if active:
        logger.warning("[INGRESS_FENCE] Untrusted ingress context activated. Fenced tools are denied at call time.")


def reset_untrusted_ingress() -> None:
    """Reset the untrusted ingress status for the current async execution context."""
    _untrusted_ingress_var.set(False)


@contextmanager
def untrusted_ingress_scope() -> Iterator[None]:
    """Mark everything run or spawned inside the block as untrusted ingress, then restore the prior state.

    Hosts that fan work out from a long-lived context (a message router's consume loop) need the
    restore: asyncio tasks copy the context when created, so tasks spawned inside the block stay fenced
    while the loop itself, and every later message it handles, is unaffected.
    """
    token = _untrusted_ingress_var.set(True)
    try:
        yield
    finally:
        _untrusted_ingress_var.reset(token)


def is_tool_allowed_under_untrusted_ingress(tool_name: str) -> bool:
    """Check whether a specific tool is permitted under an untrusted ingress session.

    Blocks if the tool name is in DISALLOWED_UNTRUSTED_TOOLS or if its resolved
    abstract permission type is in DISALLOWED_UNTRUSTED_PERMISSIONS.
    """
    clean_name = tool_name.strip().lower()
    if clean_name in DISALLOWED_UNTRUSTED_TOOLS:
        return False

    perm_type = resolve_permission_type(clean_name)
    return perm_type not in DISALLOWED_UNTRUSTED_PERMISSIONS
