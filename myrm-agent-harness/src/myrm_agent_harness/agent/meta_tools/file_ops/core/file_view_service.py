"""VIEW operation of the file tools.

[INPUT]
- strategies.strategy_factory::FileSystemStrategyFactory (POS: file-system strategy factory)
- validators.validator_chain::ValidatorChain (POS: validator chain)
- observers.observer_manager::ObserverManager (POS: observer manager)
- operation_context::OperationContext, ViewRange (POS: operation context and view range)
- result_formatter::ResultFormatter, FileContent, DirectoryListing (POS: result formatter)
- file_integrity_guard::get_file_integrity_guard (POS: records what the model has read, for the read-before-edit gate)
- context_management.infra.session_lock::get_current_chat_id (POS: current chat context)
- utils.token_estimation::estimate_content_tokens (POS: file content token estimate)
- context_management.tracking.archive_restore_runtime::evaluate_archive_refetch_for_path (POS: archived-context read budget)
- core.archive_restore_guard::evaluate_archive_full_read_before_content, format_archive_restore_block (POS: archive restore read guard)
- core.read_semaphore::get_read_semaphore (POS: read concurrency control)
- core.read_dedup::get_read_dedup_guard, DedupResult (POS: read-time dedup guard)

[OUTPUT]
- FileViewService: reads one or several paths (files with an optional line range, directories) under a concurrency
  limit, records full reads and range reads with the integrity guard, and notifies the observers.

[POS]
Read side of the file tools, split from FileOperationService so the write side (create, str_replace) stays focused.
"""

from __future__ import annotations

import asyncio
import logging
import os

from myrm_agent_harness.agent.config import FileIOConfig
from myrm_agent_harness.agent.context_management.infra.session_lock import (
    get_current_chat_id,
)
from myrm_agent_harness.utils.token_estimation import (
    estimate_content_tokens,
)

from ..observers.observer_manager import ObserverManager
from ..strategies.strategy_factory import FileSystemStrategyFactory
from ..utils.file_utils import parse_path_with_range
from ..validators.validator_chain import ValidatorChain
from .archive_restore_guard import (
    evaluate_archive_full_read_before_content,
    format_archive_restore_block,
)
from .file_integrity_guard import get_file_integrity_guard
from .operation_context import OperationContext, ViewRange
from .read_dedup import DedupResult, get_read_dedup_guard
from .read_semaphore import get_read_semaphore
from .result_formatter import DirectoryListing, FileContent, ResultFormatter

logger = logging.getLogger(__name__)


def _view_range_to_str(view_range: ViewRange | None) -> str:
    """Serialize a view range to a stable dedup key fragment."""
    if view_range is None:
        return ""
    return f"{view_range.start}:{view_range.end}"


def _format_dedup_stub(display_path: str, view_range_str: str) -> str:
    """Lightweight stub returned when a file is unchanged since the last read."""
    scope = f" (lines {view_range_str})" if view_range_str else ""
    return (
        f"[File unchanged since last read{scope}: {display_path}]\n"
        f"Content is identical to the previous read. Refer to the earlier result; "
        f"do not re-read unless the file has been modified."
    )


def _format_dedup_blocked(display_path: str, view_range_str: str, hits: int) -> str:
    """Hard block returned after repeated unchanged reads to stop tool loops."""
    scope = f" (lines {view_range_str})" if view_range_str else ""
    return (
        f"[BLOCKED: file unchanged after {hits} consecutive reads{scope}: {display_path}]\n"
        f"Content has not changed. Stop re-reading this file; use the earlier result."
    )


class FileViewService:
    """VIEW operation: files (optionally a line range) and directory listings."""

    def __init__(
        self,
        context: OperationContext,
        io_config: FileIOConfig,
        observer_manager: ObserverManager,
    ) -> None:
        self.context = context
        self.io_config = io_config
        self.observer_manager = observer_manager

    async def execute(self) -> str:
        """执行 VIEW 操作(支持批量并发读取,带并发限制)"""
        #  安全性:限制并发读取数量
        if len(self.context.paths) > self.io_config.max_concurrent_reads:
            logger.warning(
                "Concurrent read count (%d) exceeds limit (%d). Processing in batches.",
                len(self.context.paths),
                self.io_config.max_concurrent_reads,
            )

        # 获取当前事件循环的读取信号量
        semaphore = await get_read_semaphore(self.io_config)

        # 使用信号量控制并发读取
        async def _read_with_semaphore(path_str: str) -> str | Exception:
            async with semaphore:
                try:
                    return await self._view_single_path(path_str)
                except Exception as e:
                    return e

        # 并发读取多个文件
        tasks = [_read_with_semaphore(path_str) for path_str in self.context.paths]
        results = await asyncio.gather(*tasks)

        # 处理异常
        formatted_results: list[str] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                path_str = self.context.paths[i]
                error_msg = f" Error reading {path_str}: {result}"
                formatted_results.append(error_msg)
                logger.error(error_msg, exc_info=result)
            else:
                formatted_results.append(result)

        # 格式化多个结果
        return ResultFormatter.format_multiple_results(formatted_results)

    async def _view_single_path(self, path_str: str) -> str:
        """查看单个路径

        Args:
            path_str: 路径字符串(可能包含行号范围)

        Returns:
            格式化后的内容
        """
        # 解析路径和行号范围
        resolved_path, view_range = parse_path_with_range(path_str)

        # 提取显示路径(不含行号范围)
        display_path = path_str.split(":")[0] if ":" in path_str else path_str

        # 创建策略
        strategy = FileSystemStrategyFactory.create_strategy(
            resolved_path, self.context.skills, executor=self.context.executor
        )

        # 验证(使用安全配置)
        validator_chain = ValidatorChain(strategy, io_config=self.io_config, ranged_read=view_range is not None)
        await validator_chain.validate(self.context, resolved_path)

        # 检查是否是目录
        if await strategy.is_directory(resolved_path):
            entries = await strategy.list_directory(resolved_path)
            listing = DirectoryListing(path=resolved_path, display_path=display_path, entries=entries)
            return ResultFormatter.format_directory_listing(listing)

        pre_read_archive_decision = await evaluate_archive_full_read_before_content(
            strategy=strategy,
            resolved_path=resolved_path,
            view_range=view_range,
        )
        if pre_read_archive_decision is not None:
            decision, estimated_content_tokens = pre_read_archive_decision
            return format_archive_restore_block(
                decision,
                archive_path=resolved_path,
                estimated_tokens=estimated_content_tokens,
            )

        # 读取文件（返回完整行；行号范围切片统一由 ResultFormatter 处理，
        # 以正确报告总行数与续读 offset——strategy 层不二次切片）
        # 读取前先做 dedup 检查：本地文件未变时返回 stub，避免重复内容进上下文
        # 破坏 Prompt Cache。仅对可 stat mtime 的本地文件生效；MCP/云路径跳过。
        dedup_guard = get_read_dedup_guard(self.context.executor)
        dedup_hit: str | None = None
        if dedup_guard is not None:
            # 用 executor 绝对路径做 mtime 判定，避免相对路径与进程 cwd 不一致；
            # 云存储 get_actual_path 返回原路径，getmtime 抛 OSError 时安全跳过。
            actual_path = strategy.get_actual_path(resolved_path)
            try:
                mtime = os.path.getmtime(actual_path)
            except OSError:
                mtime = None
            if mtime is not None:
                view_range_str = _view_range_to_str(view_range)
                result = dedup_guard.check(actual_path, view_range_str, mtime)
                if result.kind == DedupResult.STUB:
                    dedup_hit = _format_dedup_stub(display_path, view_range_str)
                elif result.kind == DedupResult.BLOCKED:
                    dedup_hit = _format_dedup_blocked(display_path, view_range_str, result.hits)

        if dedup_hit is not None:
            return dedup_hit

        lines = await strategy.read_file(resolved_path)
        content_text = "\n".join(lines)
        estimated_content_tokens = estimate_content_tokens(content_text)
        from myrm_agent_harness.agent.context_management.tracking.archive_restore_runtime import (
            evaluate_archive_refetch_for_path,
        )

        archive_refetch_decision = evaluate_archive_refetch_for_path(
            resolved_path,
            estimated_tokens=estimated_content_tokens,
            current_chat_id=get_current_chat_id(),
            is_range_read=view_range is not None,
        )
        if archive_refetch_decision.is_archive_path and not archive_refetch_decision.allowed:
            return format_archive_restore_block(
                archive_refetch_decision,
                archive_path=resolved_path,
                estimated_tokens=estimated_content_tokens,
            )

        guard = get_file_integrity_guard(self.context.executor)
        if guard is not None:
            if view_range is None:
                guard.record_read(resolved_path, content_text)
            else:
                guard.record_read_marker(resolved_path)

        # 通知观察者
        await self.observer_manager.notify_file_viewed(resolved_path)

        # 格式化输出
        content = FileContent(
            path=resolved_path,
            display_path=display_path,
            lines=lines,
            view_range=view_range,
        )
        return ResultFormatter.format_file_content(
            content,
            max_line_length=self.io_config.max_read_line_length,
        )
