"""文件操作服务

1. 本文件的 INPUT/OUTPUT/POS 注释

[INPUT]
- strategies.strategy_factory::FileSystemStrategyFactory (POS: 文件系统策略工厂)
- validators.validator_chain::ValidatorChain (POS: 验证器链)
- observers.observer_manager::ObserverManager (POS: 观察者管理器)
- observers.snapshot_observer::SnapshotObserver (POS: 文件快照观察者,撤销支持)
- observers.format_observer::FormatObserver (POS: 编辑后自动格式化)
- observers.artifact_observer::ArtifactObserver (POS: 工件追踪)
- observers.diff_collector::DiffCollectorObserver (POS: 实时 diff 推送)
- observers.tracker_observer::TrackerObserver (POS: 生命周期记录)
- observers.activity_observer::FileActivityObserver (POS: 文件活动记录,并发冲突感知)
- operation_context::OperationContext, OperationType (POS: 操作上下文和类型)
- result_formatter::ResultFormatter, FileContent, DirectoryListing (POS: 结果格式化器)
- file_integrity_guard::get_file_integrity_guard, raise_if_integrity_rejection, raise_if_masked_writeback (POS: read/version integrity gates and masked write-back check)
- core.security.redact::command_preview (POS: masked, cut command for a log line)
- core.file_conflict_guard::check_conflict_pre_write (POS: 文件并发编辑冲突守卫)
- core.batch_str_replace::apply_batch_str_replace, compute_batch_edit_line_range (POS: Batch str-replace engine)
- core.file_view_service::FileViewService (POS: VIEW operation)
- core.read_dedup::get_read_dedup_guard (POS: 读取时 dedup 守卫,保护 Prompt Cache)
- validators.markdown_vault_write_guard::MarkdownVaultWriteGuard (POS: vault markdown FM preserve guard)
- validators.office_write_guard::OfficeWriteGuard (POS: secondary Office path text-write warnings)

[OUTPUT]
- FileOperationService: 文件操作服务类(统一的文件操作接口).VIEW 交给 FileViewService.CREATE 若覆盖已存在路径则
  notify_file_modified(pre_disk, post_write);否则 notify_file_created(post_write).
  Appends Vault/Office fidelity warnings on CREATE and STR_REPLACE responses.

[POS]
File operation service. Provides a unified file operation interface integrating strategies, validator chains, observer pipelines, concurrency control, resource limits, security validation, and concurrent subagent conflict detection. The read side lives in FileViewService.

"""

from __future__ import annotations

import logging

from myrm_agent_harness.agent.config import DEFAULT_FILE_IO_CONFIG, FileIOConfig
from myrm_agent_harness.core.security.redact import command_preview

from ..observers.activity_observer import FileActivityObserver
from ..observers.artifact_observer import ArtifactObserver
from ..observers.diff_collector import DiffCollectorObserver
from ..observers.format_observer import FormatObserver
from ..observers.observer_manager import ObserverManager
from ..observers.snapshot_observer import SnapshotObserver
from ..observers.tracker_observer import TrackerObserver
from ..strategies.strategy_factory import FileSystemStrategyFactory
from ..validators.validator_chain import ValidatorChain
from .batch_str_replace import apply_batch_str_replace, compute_batch_edit_line_range
from .file_conflict_guard import check_conflict_pre_write
from .file_integrity_guard import (
    get_file_integrity_guard,
    raise_if_integrity_rejection,
    raise_if_masked_writeback,
)
from .file_path_lock_manager import acquire_file_path_lock
from .file_view_service import FileViewService
from .operation_context import OperationContext, OperationType
from .read_dedup import get_read_dedup_guard
from .result_formatter import ResultFormatter

logger = logging.getLogger(__name__)


class FileOperationService:
    """文件操作服务

    核心服务类,整合:
    - 文件系统策略(本地/WorkspaceFS/MCP)
    - 验证器链(路径/大小/权限/敏感文件)
    - 观察者模式(Artifact/Tracker/DiffCollector)
    - 安全控制(并发限制、资源限制)
    """

    def __init__(self, context: OperationContext, io_config: FileIOConfig | None = None) -> None:
        """初始化服务

        Args:
            context: 操作上下文
            io_config: I/O 配置(可选,默认使用全局配置)
        """
        self.context = context
        self.io_config = io_config or DEFAULT_FILE_IO_CONFIG
        self.observer_manager = ObserverManager()

        # Observer registration order matters:
        # 1. SnapshotObserver FIRST — captures original content before any modification
        # 2. ArtifactObserver — registers artifacts
        # 3. TrackerObserver — records lifecycle
        # 4. FormatObserver — auto-formats after write (must run before DiffCollector)
        # 5. DiffCollectorObserver — emits real-time diffs (sees formatted content)
        # 6. FileActivityObserver — records write activity for concurrent conflict detection
        self.observer_manager.register(SnapshotObserver())
        self.observer_manager.register(ArtifactObserver())
        self.observer_manager.register(TrackerObserver())
        self.observer_manager.register(FormatObserver())
        self.observer_manager.register(DiffCollectorObserver())
        self.observer_manager.register(FileActivityObserver())

    async def execute(self) -> str:
        """执行文件操作

        Returns:
            操作结果

        Raises:
            ValueError: 参数错误
            FileNotFoundError: 文件不存在
            PermissionError: 权限不足
        """
        # 验证上下文参数
        self.context.validate()

        # 根据操作类型分发
        if self.context.operation == OperationType.VIEW:
            return await FileViewService(self.context, self.io_config, self.observer_manager).execute()

        if self.context.operation in (OperationType.CREATE, OperationType.STR_REPLACE):
            if not self.context.path:
                raise ValueError(f"{self.context.operation} operation requires 'path' parameter")

            from ..utils.path_utils import resolve_file_id_path

            resolved_lock_path = resolve_file_id_path(self.context.path)
            async with acquire_file_path_lock(resolved_lock_path):
                if self.context.operation == OperationType.CREATE:
                    return await self._execute_create()
                return await self._execute_str_replace()

        raise ValueError(f"Unknown operation: {self.context.operation}")

    async def _execute_create(self) -> str:
        """执行 CREATE 操作"""
        logger.info("_execute_create called for path: %s", self.context.path)

        if not self.context.path or self.context.file_text is None:
            raise ValueError("CREATE operation requires 'path' and 'file_text' parameters")

        # 解析文件 ID
        from ..utils.path_utils import resolve_file_id_path

        resolved_path = resolve_file_id_path(self.context.path)

        # 创建策略
        strategy = FileSystemStrategyFactory.create_strategy(
            resolved_path, self.context.skills, executor=self.context.executor
        )

        # 验证(使用安全配置)
        validator_chain = ValidatorChain(strategy, io_config=self.io_config)
        await validator_chain.validate(self.context, resolved_path)

        # Concurrent subagent conflict detection (pre-write)
        conflict_warning = check_conflict_pre_write(resolved_path, 1, self.context.file_text.count("\n") + 1)

        pre_existing = await strategy.exists(resolved_path)
        pre_content_str: str | None = None
        original_eol: str | None = None
        guard = get_file_integrity_guard(self.context.executor)
        if pre_existing:
            raise_if_integrity_rejection(
                guard,
                resolved_path,
                require_version=False,
            )
            pre_content_str = "\n".join(await strategy.read_file(resolved_path))
            raise_if_integrity_rejection(
                guard,
                resolved_path,
                disk_content=pre_content_str,
                require_version=True,
            )
            from ..utils.line_endings import detect_line_ending, normalize_line_endings

            original_eol = detect_line_ending(pre_content_str)

        file_text = self.context.file_text
        if pre_existing and original_eol:
            file_text = normalize_line_endings(file_text, original_eol)
        if pre_content_str is not None:
            raise_if_masked_writeback(resolved_path, pre_content_str, file_text)

        # 增量容错语法校验 (Delta Syntax Validator)
        from ..validators.delta_syntax_validator import DeltaSyntaxValidator

        DeltaSyntaxValidator.validate(resolved_path, file_text, pre_content=pre_content_str)

        from ..validators.markdown_vault_write_guard import MarkdownVaultWriteGuard

        file_text, vault_warnings = MarkdownVaultWriteGuard.apply(
            resolved_path,
            pre_content_str,
            file_text,
        )

        from ..validators.office_write_guard import OfficeWriteGuard

        file_text, office_warnings = OfficeWriteGuard.apply(resolved_path, file_text)

        # 写入文件
        await strategy.write_file(resolved_path, file_text)

        new_content = "\n".join(await strategy.read_file(resolved_path))

        if pre_existing and pre_content_str is not None:
            logger.info(
                "Calling observer_manager.notify_file_modified (CREATE overwrote existing) for %s",
                resolved_path,
            )
            await self.observer_manager.notify_file_modified(resolved_path, pre_content_str, new_content)
        else:
            logger.info("Calling observer_manager.notify_file_created for %s", resolved_path)
            await self.observer_manager.notify_file_created(resolved_path, new_content)

        # 执行自动校验(如果有)
        if self.context.verify_command and self.context.executor:
            from myrm_agent_harness.toolkits.code_execution.executors.models import (
                ExecutionContext,
            )

            logger.info(
                "Running verify_command on %s: %s", resolved_path, command_preview(self.context.verify_command, 200)
            )
            exec_ctx = ExecutionContext(code=self.context.verify_command, work_dir=".")
            result = await self.context.executor.execute_bash(exec_ctx)

            if not result.success:
                await strategy.delete_file(resolved_path)
                logger.warning(
                    "Verification failed for %s, file deleted. Error: %s",
                    resolved_path,
                    result.stderr,
                )
                raise ValueError(
                    f"File created but verification failed. The file has been deleted.\n"
                    f"Command: {self.context.verify_command}\n"
                    f"Exit code: {result.exit_code}\n"
                    f"Stdout: {result.stdout}\n"
                    f"Stderr: {result.stderr}\n"
                    f"Please fix the errors and try again."
                )

        # Smart Auto-Verify fallback (soft diagnostic, no rollback)
        auto_verify_report: str | None = None
        if not self.context.verify_command and self.context.executor:
            from ..validators.auto_verify import run_auto_verify

            auto_verify_report = await run_auto_verify(self.context.executor, resolved_path)

        # Record hash AFTER observers and verification so FormatObserver's changes are captured.
        # Re-read to get the post-formatted content; skip re-read when no
        # executor is available (guard would be None anyway).
        if guard is not None:
            final_content = "\n".join(await strategy.read_file(resolved_path))
            guard.record_write(resolved_path, final_content)

        # 写后失效 dedup，确保刚编辑的文件被重新读取
        dedup_guard = get_read_dedup_guard(self.context.executor)
        if dedup_guard is not None:
            dedup_guard.invalidate(resolved_path)

        logger.info("Created file: %s", resolved_path)

        response = ResultFormatter.format_success("created", resolved_path)
        if conflict_warning:
            response = f"{response}\n\n{conflict_warning}"
        if auto_verify_report:
            response = f"{response}\n{auto_verify_report}"
        return self._append_office_warnings(
            self._append_vault_warnings(response, vault_warnings),
            office_warnings,
        )

    async def _execute_str_replace(self) -> str:
        """执行 STR_REPLACE 操作（单事务批量 edits）"""
        if not self.context.path or not self.context.edits:
            raise ValueError("STR_REPLACE operation requires 'path' and non-empty 'edits' parameters")

        from ..utils.path_utils import resolve_file_id_path

        resolved_path = resolve_file_id_path(self.context.path)

        strategy = FileSystemStrategyFactory.create_strategy(
            resolved_path, self.context.skills, executor=self.context.executor
        )

        validator_chain = ValidatorChain(strategy, io_config=self.io_config)
        await validator_chain.validate(self.context, resolved_path)

        guard = get_file_integrity_guard(self.context.executor)
        raise_if_integrity_rejection(guard, resolved_path, require_version=False)

        old_content = "\n".join(await strategy.read_file(resolved_path))
        target_anchors = [edit.old_str for edit in self.context.edits if edit.old_str] if self.context.edits else None
        raise_if_integrity_rejection(
            guard,
            resolved_path,
            disk_content=old_content,
            require_version=True,
            anchor=target_anchors,
        )

        line_start, line_end = compute_batch_edit_line_range(old_content, self.context.edits)
        conflict_warning = check_conflict_pre_write(resolved_path, line_start, line_end)

        new_content, strategies = apply_batch_str_replace(old_content, self.context.edits)
        raise_if_masked_writeback(resolved_path, old_content, new_content)
        if any(s != "exact" for s in strategies):
            logger.info(
                "Batch str_replace applied with fuzzy strategies path=%s strategies=%s",
                resolved_path,
                strategies,
            )

        from ..validators.markdown_vault_write_guard import MarkdownVaultWriteGuard

        new_content, vault_warnings = MarkdownVaultWriteGuard.apply(
            resolved_path,
            old_content,
            new_content,
        )

        from ..validators.office_write_guard import OfficeWriteGuard

        new_content, office_warnings = OfficeWriteGuard.apply(resolved_path, new_content)

        await strategy.write_file(resolved_path, new_content)

        from ..validators.delta_syntax_validator import DeltaSyntaxValidator

        try:
            DeltaSyntaxValidator.validate(resolved_path, new_content, pre_content=old_content)
        except ValueError as e:
            await strategy.write_file(resolved_path, old_content)
            logger.warning(
                "Delta Syntax Validation failed for %s, changes rolled back. Error: %s",
                resolved_path,
                e,
            )
            raise

        await self.observer_manager.notify_file_modified(resolved_path, old_content, new_content)

        if self.context.verify_command and self.context.executor:
            from myrm_agent_harness.toolkits.code_execution.executors.models import (
                ExecutionContext,
            )

            logger.info(
                "Running verify_command on %s: %s", resolved_path, command_preview(self.context.verify_command, 200)
            )
            exec_ctx = ExecutionContext(code=self.context.verify_command, work_dir=".")
            result = await self.context.executor.execute_bash(exec_ctx)

            if not result.success:
                await strategy.write_file(resolved_path, old_content)
                logger.warning(
                    "Verification failed for %s, changes rolled back. Error: %s",
                    resolved_path,
                    result.stderr,
                )
                raise ValueError(
                    f"File edited but verification failed. Changes have been rolled back.\n"
                    f"Command: {self.context.verify_command}\n"
                    f"Exit code: {result.exit_code}\n"
                    f"Stdout: {result.stdout}\n"
                    f"Stderr: {result.stderr}\n"
                    f"Please fix the errors and try again."
                )

        auto_verify_report: str | None = None
        if not self.context.verify_command and self.context.executor:
            from ..validators.auto_verify import run_auto_verify

            auto_verify_report = await run_auto_verify(
                self.context.executor,
                resolved_path,
                edit_line_start=line_start,
                edit_line_end=line_end,
            )

        if guard is not None:
            final_content = "\n".join(await strategy.read_file(resolved_path))
            guard.record_write(resolved_path, final_content)

        # 写后失效 dedup，确保刚编辑的文件被重新读取
        dedup_guard = get_read_dedup_guard(self.context.executor)
        if dedup_guard is not None:
            dedup_guard.invalidate(resolved_path)

        logger.info("Replaced text in file: %s", resolved_path)

        response = ResultFormatter.format_success("replaced text in", resolved_path)
        if conflict_warning:
            response = f"{response}\n\n{conflict_warning}"
        if auto_verify_report:
            response = f"{response}\n{auto_verify_report}"
        return self._append_office_warnings(
            self._append_vault_warnings(response, vault_warnings),
            office_warnings,
        )

    @staticmethod
    def _append_vault_warnings(response: str, warnings: list[str]) -> str:
        if not warnings:
            return response
        warning_lines = "\n".join(f"Vault: {item}" for item in warnings)
        return f"{response}\n\n{warning_lines}"

    @staticmethod
    def _append_office_warnings(response: str, warnings: list[str]) -> str:
        if not warnings:
            return response
        warning_lines = "\n".join(f"Office: {item}" for item in warnings)
        return f"{response}\n\n{warning_lines}"
