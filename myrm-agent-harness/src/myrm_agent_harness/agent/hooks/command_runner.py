"""Command hook runner.

[INPUT]
- agent.hooks.command_gate (POS: 命令钩子安全网关(判模板、不判载荷)+载荷环境变量绑定+审批注入点)
- agent.hooks.types (POS: Hook 类型定义)
- core.security.bounded_communicate::communicate_bounded (POS: communicate() with a cap on each pipe, stopping the process through the caller's on_abort)
- utils.os_compat::get_process_group_kwargs, kill_spawned_group (POS: cross-platform process-group control)
- utils.text_utils::smart_truncate (POS: Head+Tail truncation with intelligent tail detection)
- utils.logger_utils (POS: 日志工具)

[OUTPUT]
- run_command_hook: run one command hook for an event and return its HookResult
- MAX_HOOK_OUTPUT_CHARS: the most output text a command hook's HookResult carries

[POS]
Runs a shell-command hook: the safety gate judges the command, the event reaches it through the environment and stdin,
and its output comes back bounded. The command runs in its own process group, so a deadline or a cancel stops
everything it started, not only the shell. A hook's output reaches the model as a block reason or a validation
failure, which no later guard caps, so it is cut here to a head and a tail.
"""

from __future__ import annotations

import asyncio
import json

from myrm_agent_harness.agent.hooks.command_gate import (
    PAYLOAD_ENV_VAR,
    approve_hook_command,
    bind_payload_reference,
    gate_hook_command,
    is_strict_source,
    payload_env_value,
)
from myrm_agent_harness.agent.hooks.types import CommandHookDefinition, HookResult
from myrm_agent_harness.core.security.bounded_communicate import communicate_bounded
from myrm_agent_harness.utils.logger_utils import get_agent_logger
from myrm_agent_harness.utils.os_compat import get_process_group_kwargs, kill_spawned_group
from myrm_agent_harness.utils.text_utils import smart_truncate

logger = get_agent_logger(__name__)

# About 160 lines of linter output: enough to name the failures, small enough not to crowd the context.
MAX_HOOK_OUTPUT_CHARS = 16_000


async def run_command_hook(hook: CommandHookDefinition, event: str, payload: dict[str, object]) -> HookResult:
    """Run *hook*'s command for *event*; the hook passes when the command exits with 0."""
    from myrm_agent_harness.core.security.process_env import (
        EnvInheritPolicy,
        build_isolated_child_env,
    )

    refusal = gate_hook_command(hook.command, strict=is_strict_source(hook))
    if refusal is not None:
        # The gate judges the hook, not the event: a refused command never
        # blocks the main flow unless the hook itself opted into fail-closed.
        if await approve_hook_command(hook, event, hook.command):
            logger.info("hooks: command hook approved via approver [event=%s source=%s]", event, hook.source.value)
        else:
            logger.warning(
                "hooks: command hook refused by safety gate [event=%s source=%s] — %s",
                event,
                hook.source.value,
                refusal,
            )
            return HookResult(
                hook_type="command",
                success=False,
                blocked=hook.block_on_failure,
                reason=f"Command refused by hook safety gate: {refusal}",
                metadata={"gate_blocked": True},
            )

    # Event data reaches the command only through the env var (see bind_payload_reference) and
    # stdin. The env var is clipped to fit one environment string; stdin carries the complete payload.
    command = bind_payload_reference(hook.command)
    payload_json = json.dumps(payload, default=str, ensure_ascii=True)
    env = build_isolated_child_env(
        base_env=None,
        extra_env={"HOOK_EVENT": event, PAYLOAD_ENV_VAR: payload_env_value(payload_json)},
        inherit_policy=EnvInheritPolicy.CORE,
    )

    process = await asyncio.create_subprocess_shell(
        command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        **get_process_group_kwargs(),
    )

    async def stop_command() -> None:
        kill_spawned_group(process.pid)

    try:
        captured = await communicate_bounded(
            process,
            timeout=hook.timeout_seconds,
            on_abort=stop_command,
            stdin_data=payload_json.encode("utf-8"),
        )
    except TimeoutError:
        return HookResult(
            hook_type="command",
            success=False,
            blocked=hook.block_on_failure,
            reason=f"Command hook timed out after {hook.timeout_seconds}s",
        )

    output = smart_truncate(
        "\n".join(
            part
            for part in (
                captured.stdout.decode("utf-8", errors="replace").strip(),
                captured.stderr.decode("utf-8", errors="replace").strip(),
            )
            if part
        ),
        MAX_HOOK_OUTPUT_CHARS,
    )
    success = process.returncode == 0
    return HookResult(
        hook_type="command",
        success=success,
        output=output,
        blocked=hook.block_on_failure and not success,
        reason=output or f"Exit code {process.returncode}",
        metadata={"returncode": process.returncode},
    )
