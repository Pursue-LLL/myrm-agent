"""BashExecutor preparation, MCP IPC scope, and skill path helpers.

[INPUT]
- agent.skills.mcp.ipc_endpoint::mcp_ipc_endpoint, ipc_proxy::CallerScope (POS: per-execution MCP IPC server and the run it serves)
- toolkits.code_execution.code_detector::code_detector, CodeType (POS: Code type detector)
- agent.skills.mcp.executor::skill_executor (POS: Skill MCP execution bridge)
- agent.skills.runtime.command_paths::rewrite_skill_paths, detect_skill_script_command (POS: Skill command path utilities)
- .error::BashExecutionError (POS: Shared error type for BashExecutor mixins and bash_code_execute_tool error surfacing)
- .constants::MCP_MIN_TIMEOUT, MCP_HOST_MARGIN_SECONDS (POS: MCP timeout floor and the margin the host keeps over the servers' call limits)

[OUTPUT]
- PreparedExecution: what one execution runs and which marker nonce authenticates its output
- BashExecutorPrepareMixin: _prepare_execution, _caller_scope, skill path rewrite

[POS]
Code-type detection, skill staging, per-execution MCP IPC server startup, and Python execution preparation.
"""

from __future__ import annotations

import logging
import math
import re
from contextlib import AsyncExitStack
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from myrm_agent_harness.agent.meta_tools.bash._executor.constants import (
    MCP_HOST_MARGIN_SECONDS,
    MCP_MIN_TIMEOUT,
)
from myrm_agent_harness.agent.meta_tools.bash._executor.error import (
    BashExecutionError,
)
from myrm_agent_harness.agent.skills.mcp.ipc_endpoint import mcp_ipc_endpoint
from myrm_agent_harness.agent.skills.mcp.ipc_proxy import CallerScope
from myrm_agent_harness.agent.skills.runtime.command_paths import (
    detect_skill_script_command,
    rewrite_skill_paths,
)
from myrm_agent_harness.toolkits.code_execution.code_detector import (
    CodeType,
    code_detector,
)
from myrm_agent_harness.toolkits.code_execution.utils import WorkspacePathResolver

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.code_execution import Workspace
    from myrm_agent_harness.toolkits.code_execution.executors.mcp_config import MCPConfigItem

logger = logging.getLogger(__name__)


class PreparedExecution(NamedTuple):
    """What one execution runs, and the nonce that authenticates the MCP markers in its output."""

    use_python_execution: bool
    code: str
    mcp_config_items: list[MCPConfigItem] | None
    trace_nonce: str | None
    """None when the execution has no IPC server, so no marker in its output can be trusted."""


class BashExecutorPrepareMixin:
    """Detect execution mode and prepare code, MCP IPC scope, and skill staging helpers."""

    @staticmethod
    def _is_read_only_scope() -> bool:
        """True when the active capability handle carries no WRITE.

        Mirrors ``LocalExecutor._scoped_context`` so the IPC server enforces the
        same scope for MCP tools that the direct Function-Calling path applies.
        """
        from myrm_agent_harness.core.security.ocap.guard import (
            CapabilityAction,
            check_capability_access,
        )

        return not check_capability_access(CapabilityAction.WRITE)

    def _caller_scope(self, session_id: str, workspace_root: str | None) -> CallerScope:
        """The run an MCP IPC server serves; the server enforces it, the script cannot restate it."""
        from myrm_agent_harness.agent.middlewares._session_context import get_agent_id

        return CallerScope(
            session_id=session_id,
            agent_id=get_agent_id() or None,
            workspace_root=workspace_root,
            readonly_workspace=self._is_read_only_scope(),
        )

    async def _prepare_execution(
        self,
        command: str,
        scope: CallerScope,
        ipc_servers: AsyncExitStack,
    ) -> PreparedExecution:
        """Detect execution mode (Python/Bash/Skill) and prepare code.

        A skill command gets its own MCP IPC server, registered on ``ipc_servers`` so it stops
        with the execution that owns the stack.
        """
        use_python_execution = False
        prepared_code = command
        mcp_config_items = None
        trace_nonce = None

        if self._enable_skill_execution and self._skill_executor:
            is_skill, skill_name = self._skill_executor.detect_skill_in_command(command)

            if is_skill and skill_name:
                use_python_execution = True
                endpoint = await ipc_servers.enter_async_context(mcp_ipc_endpoint(scope))
                logger.info(f" [MCP] Using IPC mode (socket: {endpoint.socket_path})")

                skill_context = self._skill_executor.prepare_for_execution(command=command, endpoint=endpoint)
                prepared_code = skill_context.prepared_code
                mcp_config_items = skill_context.mcp_config
                trace_nonce = endpoint.trace_nonce

        if not use_python_execution:
            detection_result = code_detector.detect(command)
            if detection_result.code_type == CodeType.PYTHON:
                use_python_execution = True
                prepared_code = detection_result.extracted_code
                logger.info(f" Python code detected ({detection_result.detection_reason})")
                if "python" in command and "-c" in command:
                    self._last_python_c_transform_hint = (
                        "Detected `python -c` wrapper — auto-rewrote to file-mode "
                        "execution. Next time pass Python source directly; the "
                        "tool auto-detects code type and avoids shell quoting bugs."
                    )
                elif "cat >" in command and "<<" in command:
                    self._last_python_c_transform_hint = (
                        "Detected `cat > file << EOF` shell wrapper — auto-rewrote to "
                        "file-mode execution. Next time pass Python source directly to "
                        "bash_code_execute_tool, or use file_write_tool + `python script.py`."
                    )

        if use_python_execution:
            self._validate_python_syntax(prepared_code, command)

        return PreparedExecution(use_python_execution, prepared_code, mcp_config_items, trace_nonce)

    def consume_python_c_transform_hint(self) -> str | None:
        """Return + clear the last ``python -c`` transform hint, if any."""
        hint: str | None = getattr(self, "_last_python_c_transform_hint", None)
        self._last_python_c_transform_hint = None  # type: ignore[assignment]
        return hint

    @staticmethod
    def _validate_python_syntax(code: str, original_command: str) -> None:
        """Pre-check extracted Python code via ``ast.parse`` before execution."""
        from myrm_agent_harness.toolkits.code_execution.python_extractor import (
            validate_python_syntax,
        )

        error = validate_python_syntax(code)
        if error is None:
            return

        is_python_c = "python" in original_command and "-c" in original_command
        hint = (
            (
                "The python3 -c command produced invalid Python after shell quote processing. "
                "Pass your Python code directly to bash_code_execute_tool WITHOUT the "
                "'python3 -c' wrapper — the tool auto-detects Python."
            )
            if is_python_c
            else (f"Pre-execution syntax check failed: {error}. Fix the code before retrying.")
        )

        raise BashExecutionError(
            f"Python syntax validation failed: {error}",
            phase="preparation",
            error_hint=hint,
            error_category="syntax",
        )

    def _inject_resilience_script(self, prepared_code: str) -> str:
        """Prepend the bash resilience init script if available."""
        script_path = Path(__file__).parent.parent / "scripts" / "resilience_init.sh"
        if not script_path.exists():
            return prepared_code
        try:
            resilience_script = script_path.read_text(encoding="utf-8")
            if resilience_script.startswith("#!/bin/bash"):
                resilience_script = resilience_script[len("#!/bin/bash") :].lstrip()
            return f"{resilience_script}\n\n{prepared_code}"
        except Exception as e:
            logger.warning(f"Failed to inject resilience script: {e}")
            return prepared_code

    def _detect_skill_from_code(self, code: str) -> str | None:
        """Detect skill name from Python import patterns or .claude/skills paths."""
        detected, skill_name = detect_skill_script_command(code)
        if detected and skill_name:
            return skill_name

        match = re.search(r"from\s+skills\.([a-zA-Z0-9_-]+)\s+import", code)
        if match:
            return match.group(1)

        match = re.search(r"import\s+skills\.([a-zA-Z0-9_-]+)", code)
        if match:
            return match.group(1)

        return None

    def _rewrite_skill_paths(self, code: str) -> tuple[str, str | None]:
        """Rewrite skill absolute paths to relative paths in code."""
        return rewrite_skill_paths(code)

    def _convert_to_container_paths(self, workspace_skill_paths: list[str], workspace: Workspace) -> list[str]:
        """Convert local absolute paths to container paths (/workspace/...)."""
        workspace_root_str = self._workspace_manager.get_workspace_path(workspace)
        if not workspace_root_str:
            logger.warning(" workspace_root is empty, cannot convert paths")
            return []

        return WorkspacePathResolver.to_container_paths(workspace_skill_paths, workspace_root_str)

    def _maybe_extend_timeout_for_mcp(
        self,
        mcp_config_items: list[MCPConfigItem] | None,
        timeout: int | None,
    ) -> int | None:
        """Raise the timeout floor while an MCP skill runs.

        The floor is the longest tool-call limit among the skill's servers plus a margin: a call held to its limit
        then ends with its own error, which names the stuck tool, instead of with the host's kill.
        """
        if not mcp_config_items:
            return timeout
        longest_call_limit = max(item.execute_timeout for item in mcp_config_items)
        floor = max(MCP_MIN_TIMEOUT, math.ceil(longest_call_limit + MCP_HOST_MARGIN_SECONDS))
        if timeout is not None and timeout >= floor:
            return timeout
        logger.warning("Auto-increased timeout %ss -> %ss for MCP skill execution", timeout, floor)
        return floor
