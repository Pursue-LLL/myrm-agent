"""Local code executor orchestrator.

[INPUT]
local._file_ops::LocalFileOpsMixin (POS: Native file I/O via pathlib with read-only guard)
local._python_subprocess::run_python_subprocess (POS: Python subprocess with sandbox and timeout)
local._background_spawn::spawn_background_process (POS: Background process spawning with sandbox)
local._bash_exec::LocalBashMixin (POS: Bash execution path: validation, audit, credential delivery, persistent shell)
local._bash_sessions::get_or_create_bash_session, close_bash_sessions, shell_grants (POS: Which persistent shell serves a command, and the granted directories it may name)
executors.common::CommandRewriter, VenvManager, ExecutionHelper (POS: Shared execution utilities)
executors.base::CodeExecutor (POS: Code executor abstract base)
code_execution.config::ExecutionConfig (POS: Execution configuration layer)
code_execution.session::LocalPersistentSession (POS: Concrete persistent shell session)

[OUTPUT]
LocalExecutor: Unified local executor for Python code and Bash commands.

[POS]
Local code execution orchestrator. Coordinates Python/Bash execution,
persistent session lifecycle, workspace binding, and composed services
(VenvManager, CommandRewriter, FileScanner, ExecutionHelper).
"""

import asyncio  # noqa: F401  # exposed as ``executor.asyncio`` for test monkey-patching
import logging
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Self

from myrm_agent_harness.core.security.ocap import CapabilityAction, check_capability_access
from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import (
    CodeExecutor,
    ExecutionContext,
    ExecutionResult,
)
from myrm_agent_harness.toolkits.code_execution.executors.common import (
    CommandRewriter,
    ExecutionHelper,
    LocalFilesScanner,
    VenvManager,
    extract_short_error,
    generate_wrapper_script,
    handle_execution_error,
)
from myrm_agent_harness.toolkits.code_execution.executors.execution_evidence import record_execution
from myrm_agent_harness.toolkits.code_execution.executors.local._bash_exec import LocalBashMixin
from myrm_agent_harness.toolkits.code_execution.executors.local._bash_sessions import (
    close_bash_sessions,
    get_or_create_bash_session,
    grant_command_paths,
    shell_grants,
)
from myrm_agent_harness.toolkits.code_execution.executors.local._file_ops import (
    LocalFileOpsMixin,
)
from myrm_agent_harness.toolkits.code_execution.executors.models import (
    AsyncProcessProtocol,
)
from myrm_agent_harness.toolkits.code_execution.utils import WorkspacePathResolver

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.code_execution.session import (
        LocalPersistentSession,
    )

logger = logging.getLogger(__name__)


class LocalExecutor(LocalBashMixin, LocalFileOpsMixin, CodeExecutor):
    """Local code executor.

    Responsibilities:
    - Execute Python code and Bash commands
    - Manage workspace binding
    - Coordinate composed services

    Composed services:
    - VenvManager: virtual environment management
    - CommandRewriter: command path rewriting
    - FileScanner: generated file scanning
    - ExecutionHelper: logging and formatting utilities
    - LocalPersistentSession: persistent Bash sessions

    File operations (read/write/grep/glob) are provided by LocalFileOpsMixin.
    """

    def __init__(self, config: ExecutionConfig, workspace_path: str | None = None):
        super().__init__(config)
        # Narrow ``CodeExecutor.config: ExecutionConfig | None`` to the strict
        # ``ExecutionConfig`` we just received so mypy can resolve ``.local``
        # without union-attr noise.
        self.config: ExecutionConfig = config

        self._venv_manager = VenvManager(config)
        self._command_rewriter = CommandRewriter()
        self._file_scanner = LocalFilesScanner()
        self._helper = ExecutionHelper()

        self._current_workspace: Path | None = None
        self._readonly_paths: list[str] = []
        self._bash_sessions: dict[str, LocalPersistentSession] = {}
        self._closed: bool = False

        if workspace_path:
            self.bind_workspace(workspace_path)

    def bind_workspace(self, workspace_path: str) -> None:
        path = Path(workspace_path)
        if self._current_workspace == path:
            return

        super().bind_workspace(workspace_path)
        self._current_workspace = path
        path.mkdir(parents=True, exist_ok=True)

        logger.debug(f" LocalExecutor: bound to workspace {workspace_path}")

    def add_readonly_path(self, path: str) -> None:
        """Register a read-only path (local mode)."""
        self._readonly_paths.append(path)

    def _resolve_work_dir(self, work_dir: str, workspace_root: Path | None) -> Path | None:
        """Resolve abstract paths (e.g. /workspace/...) to local filesystem paths.

        In container environments these paths are used directly; LocalExecutor
        adapts them to the host filesystem via WorkspacePathResolver.

        Args:
            work_dir: Abstract working directory path.
            workspace_root: Actual workspace root directory.

        Returns:
            Resolved local path, or None if resolution fails.
        """
        return WorkspacePathResolver.to_local_path(work_dir, workspace_root)

    @staticmethod
    def _scoped_context(context: ExecutionContext) -> ExecutionContext:
        """Make the workspace read-only for a run whose capability handle carries no WRITE."""
        if context.readonly_workspace or check_capability_access(CapabilityAction.WRITE):
            return context
        return replace(context, readonly_workspace=True)

    @handle_execution_error("LocalExecutor")
    async def execute(self, context: ExecutionContext) -> ExecutionResult:
        """Execute Python code (stateless — each call runs in a fresh subprocess)."""
        from myrm_agent_harness.core.security.missing_semantics import (
            SemanticsCategory,
            evaluate_missing_capability,
        )

        # Enforce Missing Semantics contract on sandbox isolation
        if self.config.local.require_sandbox_isolation:
            evaluate_missing_capability(
                SemanticsCategory.SANDBOX_ISOLATION,
                is_available=self.config.local.sandbox_available,
                detail="Python execution requires sandbox isolation, but provider is unavailable",
            )

        context = self._scoped_context(context)
        start_time = time.time()

        self._helper.log_execution_start("LocalExecutor", "Python", context.code)

        self._setup_workspace(context.workspace_root)

        # Audit potential environment variable secret leaks in python code
        try:
            from myrm_agent_harness.toolkits.code_execution.security.shell_bleed import (
                scan_content_for_env_leaks,
            )

            leak_warnings = scan_content_for_env_leaks(context.code)
            for leak_warn in leak_warnings:
                logger.warning(
                    " [LocalExecutor] Python env leak warning: reference to sensitive environment variable '%s' (pattern: '%s') in user code",
                    leak_warn.var_name,
                    leak_warn.access_pattern,
                )
        except Exception as bleed_err:
            logger.debug("Failed to perform shell bleed check on python code: %s", bleed_err)

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix="_user_code.py",
            delete=False,
            encoding="utf-8",
        ) as code_file:
            code_file.write(context.code)
            code_file_path = Path(code_file.name)

        wrapper_content = generate_wrapper_script(
            str(code_file_path),
            allow_network=context.allow_network,
            allowed_hosts=context.allowed_hosts,
            timeout=context.timeout or self.config.local.max_execution_time,
            memory_limit_mb=self.config.local.max_memory_mb,
            max_output_bytes=self.config.local.max_output_bytes,
            readonly_workspace=context.readonly_workspace,
        )

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix="_wrapper.py",
            delete=False,
            encoding="utf-8",
        ) as wrapper_file:
            wrapper_file.write(wrapper_content)
            wrapper_path = Path(wrapper_file.name)

        try:
            effective_cwd = self._resolve_work_dir(
                context.work_dir,
                (Path(context.workspace_root) if context.workspace_root else self._current_workspace),
            )

            record_execution()
            result = await self._run_subprocess(
                wrapper_path,
                context.timeout or 300,
                cwd=effective_cwd,
                env=context.env,
                allow_network=context.allow_network,
                context=context,
            )

            execution_time = time.time() - start_time

            generated_files = await self._file_scanner.scan(
                start_time,
                self._current_workspace,
            )

            if result.success:
                self._helper.log_execution_success("LocalExecutor", execution_time)

            final_result = ExecutionResult(
                success=result.success,
                result=result.result,
                stdout=result.stdout,
                stderr=result.stderr,
                error=extract_short_error(result.error) if result.error else None,
                execution_time=execution_time,
                container_id=context.session_id,
                generated_files=generated_files,
            )

            self.metrics.record(final_result, "python")
            return final_result
        finally:
            code_file_path.unlink(missing_ok=True)
            wrapper_path.unlink(missing_ok=True)

    async def _run_subprocess(
        self,
        script_path: Path,
        timeout: int,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        allow_network: bool = True,
        context: ExecutionContext | None = None,
    ) -> ExecutionResult:
        """Execute a Python script via subprocess with sandbox and timeout."""
        from myrm_agent_harness.toolkits.code_execution.executors.local._python_subprocess import (
            run_python_subprocess,
        )

        python_executable = await self._venv_manager.get_python_executable()
        return await run_python_subprocess(
            script_path=script_path,
            timeout=timeout,
            python_executable=python_executable,
            cwd=cwd,
            env=env,
            allow_network=allow_network,
            context=context,
            max_output_bytes=self.config.local.max_output_bytes,
        )

    async def spawn_background_process(self, context: ExecutionContext) -> AsyncProcessProtocol:
        """Spawn a long-running background process with full-duplex streams.

        Sandbox, environment isolation and process-tree handling live in ``_background_spawn``.
        """
        from myrm_agent_harness.toolkits.code_execution.executors.local._background_spawn import (
            spawn_background_process,
        )

        return await spawn_background_process(
            context=context,
            current_workspace=self._current_workspace,
            resolve_work_dir=self._resolve_work_dir,
            setup_workspace=self._setup_workspace,
            venv_path=self._venv_manager.get_venv_path(),
            scope_context=self._scoped_context,
        )

    def _command_whitelist(self, context: ExecutionContext) -> list[Path]:
        """The paths beside the workspace a bash command may name: the shared venv and skills, and the granted directories."""
        workspace = str(self._current_workspace) if self._current_workspace else "/tmp"
        return [
            *(self._venv_manager.command_whitelist_paths(context.additional_readonly_paths) or ()),
            *grant_command_paths(shell_grants(workspace)),
        ]

    async def _get_or_create_bash_session(
        self, context: ExecutionContext, env: dict[str, str]
    ) -> "LocalPersistentSession":
        """Get the healthy persistent shell for this context or start one."""
        return await get_or_create_bash_session(
            self._bash_sessions,
            context,
            env,
            workspace=self._current_workspace,
            max_memory_mb=self.config.local.max_memory_mb,
        )

    async def cleanup_bash_sessions(self) -> None:
        """Clean up all persistent Bash sessions."""
        await close_bash_sessions(self._bash_sessions)

    async def close(self) -> None:
        """Explicitly release bash sessions and local resources."""
        if self._closed:
            return
        self._closed = True
        await self.cleanup_bash_sessions()

    def _setup_workspace(self, workspace_path: str | None) -> None:
        """Set up the workspace directory, creating it if needed."""
        if workspace_path:
            self._current_workspace = Path(workspace_path)
            self._current_workspace.mkdir(parents=True, exist_ok=True)

    async def is_available(self) -> bool:
        """Local executor is always available."""
        return True

    def get_executor_name(self) -> str:
        """Return the executor name."""
        return "LocalExecutor"

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Async context manager exit: clean up sessions."""
        await self.cleanup_bash_sessions()
