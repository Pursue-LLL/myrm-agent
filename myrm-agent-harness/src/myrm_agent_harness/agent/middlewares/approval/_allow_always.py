"""Allow-always write-back for an approved call.

[INPUT]
- agent.security.command_allowlist_pattern::extract_shell_command (POS: shell command identity for the allowlist)
- agent.security.path_security::is_protected_instruction_file (POS: persona instruction files are never allow-always)
- .helpers::add_to_allowlist_if_needed (POS: the allowlist write)

[OUTPUT]
- should_block_allow_always: True when a call must never be remembered as always-allowed.
- try_add_to_allowlist: Remember an approved call as always-allowed unless a guard blocks it.

[POS]
The allow-always half of applying an approval decision, kept apart from the decision branches so the guard
list that decides what may be remembered reads in one place.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import ToolCall

from myrm_agent_harness.agent.security.approval_flow import DEFAULT_USER_ID
from myrm_agent_harness.agent.security.command_allowlist_pattern import (
    extract_shell_command,
)
from myrm_agent_harness.agent.security.path_security import (
    is_protected_instruction_file,
)

from .helpers import add_to_allowlist_if_needed

logger = logging.getLogger(__name__)


def _integration_mutation_blocks_allow_always(tool_call: ToolCall | dict[str, object]) -> bool:
    raw_args = tool_call.get("args", {})
    if not isinstance(raw_args, dict):
        return False
    shell_cmd = str(raw_args.get("command", "") or raw_args.get("code", "")).strip()
    if not shell_cmd:
        return False
    from myrm_agent_harness.toolkits.code_execution.security.shell_command_analyzer import (
        is_integration_mutation_command,
    )

    return is_integration_mutation_command(shell_cmd)


def should_block_allow_always(
    tool_call: ToolCall | dict[str, object],
    extra_ctx: dict[str, Any] | None,
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
    if isinstance(raw_args, dict):
        p = str(raw_args.get("path", "") or raw_args.get("file_path", "") or raw_args.get("filepath", "")).strip()
        if p and is_protected_instruction_file(p):
            return True

        cmd = str(raw_args.get("command", "") or raw_args.get("code", "")).strip()
        if cmd:
            from myrm_agent_harness.toolkits.code_execution.security.shell_command_analyzer import (
                is_protected_instruction_mutation_command,
            )

            if is_protected_instruction_mutation_command(cmd):
                return True

    return _integration_mutation_blocks_allow_always(tool_call)


async def try_add_to_allowlist(
    tool_call: ToolCall | dict[str, object],
    extra_ctx: dict[str, Any] | None,
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
    shell_command = extract_shell_command(tool_args if isinstance(tool_args, dict) else None)
    await add_to_allowlist_if_needed(
        allow_always,
        user_id,
        permission_type,
        allowlist_tool_name,
        args_hashes.get(idx),
        tool_command=shell_command,
        agent_id=agent_id,
        ttl_seconds=ttl_seconds,
        session_id=session_id,
    )
