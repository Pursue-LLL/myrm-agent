"""Bash execution mixin for LocalExecutor.

[INPUT]
local._command_env::build_command_env, scrubbed_user_env (POS: What one bash command may read: skill settings and its credentials)
executors.common::CommandRewriter, ExecutionHelper, LocalFilesScanner, VenvManager, handle_execution_error (POS: Shared execution utilities)
executors.execution_evidence::record_execution (POS: Execution evidence recorder)
code_execution.interceptor::trigger_bash_action_hook (POS: Bash action snapshot hook)
code_execution.security.validator::validate_command; core.security.process_env::sanitize_env (POS: Command validation and environment sanitising)
core.security.ocap::CapabilityAction, enforce_capability_access (POS: Capability scope)
core.security.redact::command_preview (POS: masked, cut command for a log line)

[OUTPUT]
LocalBashMixin: ``execute_bash`` (validated, audited run in the persistent shell with the command's own environment),
``execute_bash_stream``, command preparation and the sanitized environment a shell starts with.

[POS]
The bash path of the local executor. It is the only place that turns the command an agent issued
(``ExecutionContext.original_code``) into a run: validation, shell-bleed audit and credential delivery use the issued
text, the shell receives the prepared script.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from myrm_agent_harness.core.security.ocap import CapabilityAction, enforce_capability_access
from myrm_agent_harness.core.security.redact import command_preview
from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import ExecutionContext, ExecutionResult
from myrm_agent_harness.toolkits.code_execution.executors.common import (
    CommandRewriter,
    ExecutionHelper,
    LocalFilesScanner,
    VenvManager,
    handle_execution_error,
)
from myrm_agent_harness.toolkits.code_execution.executors.execution_evidence import record_execution
from myrm_agent_harness.toolkits.code_execution.executors.local._command_env import (
    build_command_env,
    scrubbed_user_env,
)
from myrm_agent_harness.toolkits.code_execution.executors.models import ExecutionMetrics
from myrm_agent_harness.toolkits.code_execution.interceptor import trigger_bash_action_hook

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.code_execution.session import LocalPersistentSession

logger = logging.getLogger(__name__)


class _BashHost(Protocol):
    """What the bash path needs from the executor it is mixed into."""

    config: ExecutionConfig
    metrics: ExecutionMetrics
    _helper: ExecutionHelper
    _file_scanner: LocalFilesScanner
    _command_rewriter: CommandRewriter
    _venv_manager: VenvManager
    _current_workspace: Path | None

    def _scoped_context(self, context: ExecutionContext) -> ExecutionContext: ...

    def _resolve_work_dir(self, work_dir: str, workspace_root: Path | None) -> Path | None: ...

    def _command_whitelist(self, context: ExecutionContext) -> list[Path]: ...

    def _setup_workspace(self, workspace_path: str | None) -> None: ...

    async def _get_or_create_bash_session(
        self, context: ExecutionContext, env: dict[str, str]
    ) -> LocalPersistentSession: ...

    async def _prepare_bash_command(self, command: str) -> str: ...

    def _build_bash_env(self, user_env: dict[str, str] | None) -> dict[str, str]: ...


class LocalBashMixin:
    """The bash methods of ``LocalExecutor``; the host supplies the state described by ``_BashHost``."""

    @handle_execution_error("LocalExecutor")
    async def execute_bash(self: _BashHost, context: ExecutionContext) -> ExecutionResult:
        """Execute a Bash command in a persistent session (state persists across calls)."""
        from myrm_agent_harness.core.security.missing_semantics import (
            SemanticsCategory,
            evaluate_missing_capability,
        )
        from myrm_agent_harness.toolkits.code_execution.security.validator import (
            validate_command,
        )

        # Enforce Missing Semantics contract on sandbox isolation
        if self.config.local.require_sandbox_isolation:
            evaluate_missing_capability(
                SemanticsCategory.SANDBOX_ISOLATION,
                is_available=self.config.local.sandbox_available,
                detail="Bash execution requires sandbox isolation, but provider is unavailable",
            )

        context = self._scoped_context(context)
        start_time = time.time()
        command = context.code
        issued_command = context.original_code or command

        self._helper.log_execution_start("LocalExecutor", "Bash (Persistent)", command)

        # Resolve working directory
        workspace = Path(context.workspace_root) if context.workspace_root else self._current_workspace
        effective_cwd = self._resolve_work_dir(context.work_dir, workspace)

        # Security validation
        effective_allowed_hosts = None
        if context.allow_network and context.allowed_hosts is not None:
            effective_allowed_hosts = context.allowed_hosts

        validation_result = validate_command(
            issued_command,
            workspace_path=effective_cwd,
            additional_paths=self._command_whitelist(context),
            allowed_hosts=effective_allowed_hosts,
        )

        enforce_capability_access(CapabilityAction.EXECUTE, str(effective_cwd))

        # Audit potential environment variable secret leaks in command
        try:
            from myrm_agent_harness.toolkits.code_execution.security.shell_bleed import (
                scan_content_for_env_leaks,
            )

            leak_warnings = scan_content_for_env_leaks(issued_command)
            for leak_warn in leak_warnings:
                logger.warning(
                    " [LocalExecutor] Shell bleed warning: reference to sensitive environment variable '%s' (pattern: '%s') in command",
                    leak_warn.var_name,
                    leak_warn.access_pattern,
                )
        except Exception as bleed_err:
            logger.debug("Failed to perform shell bleed check on command: %s", bleed_err)

        if not validation_result.is_safe:
            error_msg = f"Command blocked for security reasons: {validation_result.reason}"
            logger.warning(f" [LocalExecutor] {error_msg}")
            blocked_result = ExecutionResult(
                success=False,
                error=error_msg,
                error_category="permission_denied",
                stderr=error_msg,
                execution_time=time.time() - start_time,
            )
            self.metrics.record(blocked_result, "bash")
            return blocked_result

        await trigger_bash_action_hook(
            workspace_path=(str(self._current_workspace) if self._current_workspace else "/tmp"),
            command=command,
            session_id=context.session_id,
        )

        self._setup_workspace(str(effective_cwd) if effective_cwd else None)

        command = await self._prepare_bash_command(command)

        env = self._build_bash_env(context.env)
        session = await self._get_or_create_bash_session(context, env)
        command_env = build_command_env(context.env, context.allowed_credential_issuers, issued_command)

        timeout = context.timeout or self.config.local.max_execution_time
        record_execution()
        session_result = await session.execute(command, timeout, cancel_token=context.cancel_token, env=command_env)

        execution_time = time.time() - start_time

        generated_files = await self._file_scanner.scan(
            start_time,
            self._current_workspace,
        )

        if session_result.success:
            self._helper.log_execution_success("LocalExecutor", execution_time)
        else:
            logger.warning(
                " [LocalExecutor] Bash exit code: %d (%s) | cmd: %s",
                session_result.exit_code,
                self._helper.format_execution_time(execution_time),
                command_preview(command, 200),
            )
            if session_result.stderr:
                logger.warning(f" [LocalExecutor] Bash stderr: {session_result.stderr}")
            if session_result.stdout:
                logger.info(f" [LocalExecutor] Bash stdout: {session_result.stdout}")

        from myrm_agent_harness.core.security.redact import redact_sensitive_text
        from myrm_agent_harness.toolkits.code_execution.utils.stderr_filter import filter_stderr_text

        clean_stdout = redact_sensitive_text(session_result.stdout) if session_result.stdout else session_result.stdout
        clean_stderr = redact_sensitive_text(session_result.stderr) if session_result.stderr else session_result.stderr
        error_detail = session_result.error

        if clean_stderr:
            filtered_stderr = filter_stderr_text(clean_stderr)
            if filtered_stderr.has_critical_error and not error_detail:
                error_detail = filtered_stderr.filtered_error_text or clean_stderr

        final_result = ExecutionResult(
            success=session_result.success,
            result=session_result.exit_code,
            stdout=clean_stdout,
            stderr=clean_stderr,
            error=error_detail,
            execution_time=execution_time,
            container_id=context.session_id,
            generated_files=generated_files,
            exit_code=session_result.exit_code,
        )
        self.metrics.record(final_result, "bash")
        return final_result

    async def execute_bash_stream(self: _BashHost, context: ExecutionContext) -> AsyncIterator[str]:
        """Execute a Bash command with real-time line-by-line output streaming."""
        from myrm_agent_harness.toolkits.code_execution.security.validator import (
            validate_command,
        )

        context = self._scoped_context(context)
        command = context.code
        issued_command = context.original_code or command
        workspace = Path(context.workspace_root) if context.workspace_root else self._current_workspace
        effective_cwd = self._resolve_work_dir(context.work_dir, workspace)

        effective_allowed_hosts = None
        if context.allow_network and context.allowed_hosts is not None:
            effective_allowed_hosts = context.allowed_hosts

        validation_result = validate_command(
            command,
            workspace_path=effective_cwd,
            additional_paths=self._command_whitelist(context),
            allowed_hosts=effective_allowed_hosts,
        )

        if not validation_result.is_safe:
            yield f"[ERROR] Command blocked: {validation_result.reason}\n"
            return

        enforce_capability_access(CapabilityAction.EXECUTE, str(effective_cwd))

        self._setup_workspace(str(effective_cwd) if effective_cwd else None)
        command = await self._prepare_bash_command(command)
        env = self._build_bash_env(context.env)
        session = await self._get_or_create_bash_session(context, env)
        command_env = build_command_env(context.env, context.allowed_credential_issuers, issued_command)

        timeout = context.timeout or self.config.local.max_execution_time
        record_execution()
        async for chunk in session.execute_stream(command, timeout, cancel_token=context.cancel_token, env=command_env):
            yield chunk

    async def _prepare_bash_command(self: _BashHost, command: str) -> str:
        """Rewrite workspace paths, search commands, and pip commands for the local environment."""
        command = self._command_rewriter.rewrite_workspace_paths(
            command,
            self._current_workspace,
        )
        command = self._command_rewriter.rewrite_search_commands(command)
        return await self._venv_manager.rewrite_pip_command(command)

    def _build_bash_env(self: _BashHost, user_env: dict[str, str] | None) -> dict[str, str]:
        """Build the sanitized environment a bash shell starts with.

        Credentials are not part of it: a shell outlives the commands it runs, so they travel with each command
        (``build_command_env``) instead of being baked into the shell.
        """
        from myrm_agent_harness.core.security.process_env import sanitize_env

        env = sanitize_env(os.environ.copy())

        venv_path = self._venv_manager.get_venv_path()
        if venv_path.exists():
            env["VIRTUAL_ENV"] = str(venv_path)
            venv_bin = str(venv_path / "bin")
            env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")

        if user_env:
            env.update(scrubbed_user_env(user_env))
            logger.debug(f" User env vars: {list(user_env.keys())}")

        # Post-override scrubbing guarantee: strip any non-inheritable host secrets from base/user env (Codex #38941)
        from myrm_agent_harness.core.security.process_env import (
            is_non_inheritable_env_var,
        )

        for k in list(env.keys()):
            if is_non_inheritable_env_var(k):
                env.pop(k, None)

        try:
            from myrm_agent_harness.core.context_vars import user_timezone_var

            user_tz = user_timezone_var.get()
            if user_tz:
                env["MYRM_USER_TIMEZONE"] = user_tz
        except LookupError:
            pass

        return env
