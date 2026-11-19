"""Allow-always write-back for an approved call.

[INPUT]
- agent.security.command_rules::command_text, launch_command (POS: the text a command-bearing tool runs, and the command a call starts)
- agent.security.path_security::is_protected_instruction_file (POS: persona instruction files are never allow-always)
- core.security.tool_registry::host_file_paths, resolve_permission_type, resolve_safety_metadata (POS: the files a call names under any argument spelling, the permission type it asks for, and whether its tool only reads)
- toolkits.code_execution.security.protected_instruction_command::protected_instruction_mutation_target (POS: whether a command writes a protected instruction file)
- toolkits.code_execution.security.shell_command_analyzer::is_integration_mutation_command (POS: whether a command mutates an integration)
- .helpers::add_to_allowlist_if_needed (POS: the allowlist write)

[OUTPUT]
- protected_instruction_file_target: the protected instruction file a tool that is not read-only names in a file argument
- should_block_allow_always: True when a call must never be remembered as always-allowed.
- try_add_to_allowlist: Remember an approved call as always-allowed unless a guard blocks it.

[POS]
The allow-always half of applying an approval decision, kept apart from the decision branches so the guard
list that decides what may be remembered reads in one place. The pending-approval annotation reads the same
``protected_instruction_file_target``, so a card hides "Allow Always" exactly when this guard would refuse it.
"""

from __future__ import annotations

import logging

from langchain_core.messages import ToolCall

from myrm_agent_harness.agent.security.approval_flow import DEFAULT_USER_ID
from myrm_agent_harness.agent.security.command_rules import command_text, launch_command
from myrm_agent_harness.agent.security.path_security import (
    is_protected_instruction_file,
)
from myrm_agent_harness.core.security.tool_registry import (
    host_file_paths,
    resolve_permission_type,
    resolve_safety_metadata,
)

from .helpers import add_to_allowlist_if_needed

logger = logging.getLogger(__name__)


def protected_instruction_file_target(tool_name: str, tool_input: dict[str, object]) -> str | None:
    """The protected instruction file a tool that is not read-only names in a file argument; None when it names none.

    The engine asks for the writes it classifies (the file tools, shell commands) under a coded reason, and the
    approval stages read that code. A tool it cannot classify, such as an MCP file server's write tool, is read by its
    file arguments instead. A read-only tool names a file to open it, never to change it.
    """
    if resolve_safety_metadata(tool_name).is_read_only:
        return None
    return next((path for path in host_file_paths(tool_input) if is_protected_instruction_file(path)), None)


def _command_of(tool_call: ToolCall | dict[str, object]) -> str:
    """The text the call runs; empty for a tool that runs no command."""
    raw_args = tool_call.get("args") or tool_call.get("arguments") or {}
    if not isinstance(raw_args, dict):
        return ""
    permission = resolve_permission_type(str(tool_call.get("name", "")), raw_args)
    return command_text(permission, raw_args)


def should_block_allow_always(
    tool_call: ToolCall | dict[str, object],
    extra_ctx: dict[str, object] | None,
) -> bool:
    """Unified guard: returns True when allowAlways must be blocked."""
    from myrm_agent_harness.agent.middlewares._session_context import (
        get_managed_approval_policy,
    )
    from myrm_agent_harness.agent.security.managed_policy_gates import (
        allow_always_writes_blocked,
    )

    if allow_always_writes_blocked(get_managed_approval_policy()):
        return True
    if extra_ctx and (
        extra_ctx.get("high_risk")
        or extra_ctx.get("smart_denied")
        or extra_ctx.get("hide_allow_always")
        or extra_ctx.get("requires_dual_insurance")
        or extra_ctx.get("socially_irreversible")
        or extra_ctx.get("irreversible_destructive")
        or extra_ctx.get("auto_mode_suspended")
        or extra_ctx.get("protected_instruction")
    ):
        return True

    raw_args = tool_call.get("args") or tool_call.get("arguments") or {}
    if isinstance(raw_args, dict) and protected_instruction_file_target(str(tool_call.get("name", "")), raw_args):
        return True

    command = _command_of(tool_call)
    if not command:
        return False
    from myrm_agent_harness.toolkits.code_execution.security.protected_instruction_command import (
        protected_instruction_mutation_target,
    )
    from myrm_agent_harness.toolkits.code_execution.security.shell_command_analyzer import (
        is_integration_mutation_command,
    )

    return protected_instruction_mutation_target(command) is not None or is_integration_mutation_command(command)


async def try_add_to_allowlist(
    tool_call: ToolCall | dict[str, object],
    extra_ctx: dict[str, object] | None,
    allow_always: bool | dict[str, bool],
    permission_type: str,
    allowlist_tool_name: str,
    idx: int,
    args_hashes: dict[int, str | None],
    ttl_seconds: int | float | None = None,
) -> None:
    """Write to allowlist if allow_always is set and not blocked by security guards."""
    if not allow_always:
        return
    if should_block_allow_always(tool_call, extra_ctx):
        tool_name = tool_call.get("name", "unknown")
        logger.warning(
            "[APPROVAL] Ignoring allow_always for high-risk/restricted operation on %s",
            tool_name,
        )
        return
    from myrm_agent_harness.agent.middlewares._session_context import (
        get_agent_id,
        get_approval_session,
        get_approval_user_id,
    )

    user_id = get_approval_user_id() or DEFAULT_USER_ID
    agent_id = get_agent_id() or None
    session_id = get_approval_session() or None
    tool_args = tool_call.get("args", {})
    await add_to_allowlist_if_needed(
        allow_always,
        user_id,
        permission_type,
        allowlist_tool_name,
        args_hashes.get(idx),
        tool_command=launch_command(permission_type, tool_args if isinstance(tool_args, dict) else None),
        agent_id=agent_id,
        ttl_seconds=ttl_seconds,
        session_id=session_id,
    )
