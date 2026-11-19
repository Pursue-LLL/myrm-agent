"""Bash code execution tool (aggregate root).

[INPUT]
- ._security.preflight_checks (POS: Security preflight checks)
- ._executor.executor::BashExecutor (POS: Bash executor aggregate root. MRO: Execute → Background → Prepare → Context (locked by architecture tests).)
- ._tool.helpers (POS: BashInput, OS hint, context tracking, skill storage path resolution)
- ._tool.formatting (POS: Output formatting and truncation)
- ._tool.evicted_emit::emit_result_evicted_refs (POS: announces the streams a finished call stored in full)
- ._tool.failure::build_failure_error (POS: the ToolError a failed call hands to the model)
- ._tool.background_listeners (POS: Background ptc_notify listeners)
- ._background.poll::report_result_read (POS: tells the wakeup handler the model now holds a finished job's result)
- ._tool.multimodal (POS: Vision ContentBlock return path)
- ._tool.exit_semantics (POS: Exit-code semantic interpretation)
- .._context_recovery::ensure_executor, restore_context_vars (POS: Executor ContextVar recovery)
- toolkits.code_execution.code_detector::runs_as_python (POS: whether a command runs as Python or in a shell)

[OUTPUT]
- create_bash_code_execute_tool: Factory creating the bash_code_execute_tool LangChain Tool
- Re-exported helpers for tests (see __all__)

[POS]
Bash code execution LangChain tool aggregate root.
Public import path: ``from ...bash_code_execute_tool import create_bash_code_execute_tool``.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from langchain_core.runnables import RunnableConfig
from langchain_core.tools.convert import tool

from myrm_agent_harness.agent.context_management.context import (
    extract_context_from_runnable_config,
)
from myrm_agent_harness.agent.meta_tools._context_recovery import (
    ensure_executor,
    restore_context_vars,
)
from myrm_agent_harness.agent.meta_tools.bash._background.poll import report_result_read
from myrm_agent_harness.agent.meta_tools.bash._background.registry import (
    get_background_registry,
)
from myrm_agent_harness.agent.meta_tools.bash._executor.auto_yield import (
    build_auto_yield_return,
    resolve_yield_seconds,
    should_auto_yield,
    wait_for_yield_window,
)
from myrm_agent_harness.agent.meta_tools.bash._security.path_guard import (
    check_sensitive_paths,
)
from myrm_agent_harness.agent.meta_tools.bash._security.preflight_checks import (
    check_command_url_exfiltration,
    check_destructive_commands,
    check_install_packages,
    check_interactive_command,
    check_myrm_tools_import,
    check_unquoted_background_ampersand,
)
from myrm_agent_harness.agent.meta_tools.bash._tool.background_listeners import (
    build_background_listeners,
    classify_background_exit,
)
from myrm_agent_harness.agent.meta_tools.bash._tool.evicted_emit import (
    emit_result_evicted_refs,
)
from myrm_agent_harness.agent.meta_tools.bash._tool.exit_semantics import (
    interpret_exit_code,
)
from myrm_agent_harness.agent.meta_tools.bash._tool.failure import (
    build_failure_error,
)
from myrm_agent_harness.agent.meta_tools.bash._tool.formatting import (
    format_result,
    truncate_bash_output,
)
from myrm_agent_harness.agent.meta_tools.bash._tool.helpers import (
    CONTEXT_PATH_PATTERNS,
    BashInput,
    get_os_hint,
    resolve_skill_storage_paths,
    track_context_access_in_command,
)
from myrm_agent_harness.agent.meta_tools.bash._tool.multimodal import (
    MAX_IMAGES_PER_RETURN,
    maybe_build_image_blocks,
)
from myrm_agent_harness.agent.meta_tools.bash._tool.tool_description import (
    resolve_bash_code_execute_tool_description,
)
from myrm_agent_harness.core.security.redact import command_preview
from myrm_agent_harness.toolkits.code_execution.code_detector import runs_as_python

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from myrm_agent_harness.backends.skills.types import SkillMetadata

logger = logging.getLogger(__name__)

# Test-oriented re-exports from the bash_code_execute_tool aggregate module.
_interpret_exit_code = interpret_exit_code
_format_result = format_result
_truncate_bash_output = truncate_bash_output
_get_os_hint = get_os_hint
_restore_context_vars = restore_context_vars
_track_context_access_in_command = track_context_access_in_command
_build_background_listeners = build_background_listeners
_classify_background_exit = classify_background_exit
_maybe_build_image_blocks = maybe_build_image_blocks


def create_bash_code_execute_tool(
    skills: list[SkillMetadata] | None = None,
    *,
    skill_env_map: dict[str, dict[str, str]] | None = None,
    global_env: dict[str, str] | None = None,
    locale: str | None = None,
) -> BaseTool:
    """Create the bash code execution LangChain tool."""

    skill_paths = resolve_skill_storage_paths(skills or [])
    skill_oauth_issuers = {s.name: s.oauth_issuer for s in (skills or []) if s.oauth_issuer and s.name}

    description = resolve_bash_code_execute_tool_description(locale) + get_os_hint(locale=locale)

    @tool("bash_code_execute_tool", description=description, args_schema=BashInput)
    async def bash_func(
        reason: str,
        command: str,
        timeout: int | None = None,
        run_in_background: bool = False,
        yield_after_seconds: int | None = None,
        *,
        config: RunnableConfig,
    ) -> dict[str, object] | Sequence[object]:
        """Execute a bash command, python script, or skill invocation."""
        intent = reason.strip()
        command = command.strip()
        if logger.isEnabledFor(logging.INFO):
            logger.info("BASH_EXECUTE intent=%r command_preview=%r", intent, command_preview(command, 200))

        if ".context/" in command:
            paths = []
            for pattern in CONTEXT_PATH_PATTERNS:
                paths.extend(pattern.findall(command))

            for path in set(paths):
                if path:
                    logger.info("CONTEXT_ACCESS path=%s method=bash_command", path)

        try:
            context = extract_context_from_runnable_config(config)
            workspace_root = str(context.get("workspace_path", "")) or None

            check_command_url_exfiltration(command)
            check_sensitive_paths(command)
            check_destructive_commands(command)
            check_myrm_tools_import(command, workspace_root=workspace_root)

            interactive_msg = check_interactive_command(command)
            if interactive_msg is not None and not run_in_background:
                from myrm_agent_harness.utils.errors import ToolError

                raise ToolError(
                    message=interactive_msg,
                    user_hint=interactive_msg,
                    diagnostic_info={"interactive_required": True},
                )

            auto_yield = should_auto_yield(
                command=command,
                run_in_background=run_in_background,
                yield_after_seconds=yield_after_seconds,
            )
            # `&` is a shell operator, so the guard only concerns commands a shell reads: not Python source,
            # which the wrapper runs (a whitelisted build/test command is spawned in a shell either way).
            python_source = not auto_yield and runs_as_python(command, run_in_background=run_in_background)

            if not run_in_background and not python_source:
                bg_amp_msg = check_unquoted_background_ampersand(command)
                if bg_amp_msg is not None:
                    from myrm_agent_harness.utils.errors import ToolError

                    raise ToolError(
                        message=bg_amp_msg,
                        user_hint="Use run_in_background=True for background jobs, or '&&' for chained commands.",
                        diagnostic_info={"detached_background_prohibited": True},
                    )

            await check_install_packages(command)

            session_id = str(context.get("session_id", "")) or None

            from myrm_agent_harness.agent.meta_tools.bash._executor.executor import (
                BashExecutor,
            )
            from myrm_agent_harness.agent.skills.mcp.notify_registry import (
                session_scope,
            )

            executor = ensure_executor(config)
            restore_context_vars(context, executor)
            bash_executor = BashExecutor(executor=executor)
            if skill_oauth_issuers:
                bash_executor.set_skill_oauth_issuers(skill_oauth_issuers)
            if skill_env_map:
                bash_executor.set_skill_env_map(skill_env_map)
            if global_env:
                bash_executor.set_global_env(global_env)

            if run_in_background or auto_yield:
                if not session_id:
                    from myrm_agent_harness.utils.errors import ToolError

                    raise ToolError(
                        message="run_in_background requires a bound session_id.",
                        user_hint="Background jobs are scoped per chat session.",
                    )
                finish_listener, progress_listener = build_background_listeners(session_id=session_id, config=config)
                info = await bash_executor.spawn_background(
                    command=command,
                    session_id=session_id,
                    finish_listener=finish_listener,
                    progress_listener=progress_listener,
                )
                from myrm_agent_harness.utils.event_utils import dispatch_custom_event

                await dispatch_custom_event(
                    "ptc_notify",
                    {
                        "event": "ptc_notify",
                        "level": "info",
                        "message": f"Background job pid={info.pid} started",
                        "category": f"background:{info.pid}:started",
                        "session_id": session_id,
                    },
                    config=config,
                )

                if auto_yield and not run_in_background:
                    yield_seconds = resolve_yield_seconds(yield_after_seconds)
                    assert yield_seconds is not None
                    final_info = await wait_for_yield_window(
                        get_background_registry(),
                        info.pid,
                        yield_seconds=yield_seconds,
                    )
                    if final_info is not None:
                        # A job that ended inside the window returns its exit and output tail through this call.
                        report_result_read(final_info)
                        return build_auto_yield_return(
                            info=final_info,
                            yield_seconds=yield_seconds,
                        )

                return {
                    "content": (
                        f"Background process started.\n"
                        f"  job_id: {info.job_id}\n"
                        f"  pid: {info.pid}\n"
                        f"  command: {info.command}\n"
                        f"  status: {info.status}\n\n"
                        "Use bash_process_tool(action='output', pid=...) to poll stdout/stderr, "
                        "bash_process_tool(action='submit_stdin', pid=..., data=...) for interactive "
                        "prompts, or bash_process_tool(action='kill', pid=...) to stop it. "
                        "GUI users can also send input from the Activity panel."
                    ),
                    "metadata": {
                        "background": True,
                        "job_id": info.job_id,
                        "pid": info.pid,
                        "status": info.status,
                    },
                }

            async with session_scope(session_id, config):
                result = await bash_executor.execute(
                    command,
                    session_id=session_id,
                    skill_paths=skill_paths,
                    timeout=timeout,
                )

            transform_hint = bash_executor.consume_python_c_transform_hint()
            if transform_hint:
                from myrm_agent_harness.utils.event_utils import dispatch_custom_event

                await dispatch_custom_event(
                    "ptc_notify",
                    {
                        "event": "ptc_notify",
                        "level": "info",
                        "message": transform_hint,
                        "category": "code_rewrite",
                        "session_id": session_id,
                    },
                    config=config,
                )

            if session_id:
                await track_context_access_in_command(command, session_id)

            formatted_content, is_truncated, trunc_meta = format_result(result, command)

            office_warnings = result.get("office_warnings")
            if isinstance(office_warnings, list) and office_warnings:
                warning_lines = "\n".join(f"Office: {item}" for item in office_warnings if isinstance(item, str))
                if warning_lines:
                    formatted_content = f"{formatted_content}\n\n{warning_lines}"

            if is_truncated:
                from myrm_agent_harness.utils.event_utils import dispatch_custom_event

                await dispatch_custom_event(
                    "agent_status",
                    {"event": "tool_truncated", "tool": "bash", "metadata": trunc_meta},
                    config=config,
                )

            await emit_result_evicted_refs(result, formatted_content=formatted_content, config=config)

            metadata: dict[str, object] = {}
            if result.get("mcp_metadata") and isinstance(result["mcp_metadata"], dict):
                metadata = result["mcp_metadata"]

            generated = result.get("generated_files")
            generated_files: list[str] = list(generated) if isinstance(generated, list) else []
            blocks = await maybe_build_image_blocks(
                text_content=formatted_content,
                generated_files=generated_files,
                context=context,
            )
            if blocks is not None:
                return blocks

            return {
                "content": formatted_content,
                "metadata": metadata,
            }
        except Exception as e:
            from myrm_agent_harness.utils.errors import ToolError

            if isinstance(e, ToolError):
                raise

            raise await build_failure_error(e, command=command, config=config) from e

    return bash_func


__all__ = [
    "MAX_IMAGES_PER_RETURN",
    "BashInput",
    "_build_background_listeners",
    "_classify_background_exit",
    "_format_result",
    "_get_os_hint",
    "_interpret_exit_code",
    "_maybe_build_image_blocks",
    "_restore_context_vars",
    "_track_context_access_in_command",
    "_truncate_bash_output",
    "create_bash_code_execute_tool",
]
