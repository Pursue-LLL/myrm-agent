"""内容搜索工具（Claude Code 兼容）

[INPUT]
- langchain.tools::tool (POS: LangChain 工具装饰器)
- pydantic::BaseModel, Field (POS: 参数验证)
- agent.config.file_io::FileIOConfig (POS: I/O 配置)
- agent.security.redact::redact_sensitive_text (POS: 工具输出脱敏，防止凭证泄露到 LLM 上下文)
- _redaction::redact_matches (POS: 逐文件按类型脱敏匹配行，源码里含 token 的类型名/变量名不被误遮)
- agent.meta_tools._context_recovery::ensure_executor (POS: Executor ContextVar recovery)
- regex_validator::RegexValidator (POS: 正则表达式验证器，防止 ReDoS)
- utils.lru_cache::LRUCache (POS: LRU 缓存)
- _formatter (POS: Grep flat path:line output formatter with line truncation)
- fallback_discovery::collect_candidate_files (POS: 候选文件发现策略：Python 档发现)
- fallback_search::search_files (POS: Python 档内容搜索：mmap 扫描、分批并发、结果与时间上限)
- rg_traversal::rg_traversal_args (POS: ripgrep 档遍历策略，与 Python 档选出同一批文件)
- glob_match::compile_glob, is_match_all, normalize_glob (POS: 两档共用的 glob 语义：锚定、**、花括号)
- _rg_runner::run_rg (POS: ripgrep 子进程生命周期：提前终止、超时回收)

[OUTPUT]
- GrepInput: Grep 工具输入参数模型
- create_grep_tool: 创建 Grep 工具的工厂函数

[POS]
Content search tool (Claude Code compatible). Searches file contents for matching text patterns
with regex and literal (--fixed-strings) modes, flat path:line output and intelligent line truncation.
Two search tiers choose the same files (``rg_traversal`` for ripgrep, ``fallback_discovery`` for the
Python tier); ripgrep runs first, and the Python tier takes over when ripgrep is missing or fails
without producing a result.

"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from langchain.tools import tool
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from myrm_agent_harness.agent.config import DEFAULT_FILE_IO_CONFIG, FileIOConfig
from myrm_agent_harness.agent.meta_tools._context_recovery import ensure_executor
from myrm_agent_harness.agent.security.redact import redact_sensitive_text
from myrm_agent_harness.utils.errors import ToolError
from myrm_agent_harness.utils.locale import is_chinese

from ._formatter import format_grep_results
from ._redaction import redact_matches
from ._rg_runner import run_rg
from .fallback_discovery import collect_candidate_files
from .fallback_search import search_files
from .glob_match import compile_glob, is_match_all, normalize_glob
from .path_hint import format_path_not_found_hint, mcp_namespace_error, suggest_similar_paths
from .regex_validator import RegexValidator
from .rg_traversal import rg_traversal_args
from .skill_path_filter import get_disabled_skill_roots, is_under_disabled_skill_root

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


#  性能优化：ripgrep 检测（只检测一次）
@lru_cache(maxsize=1)
def _has_ripgrep() -> bool:
    """检测系统是否有 ripgrep"""
    try:
        result = subprocess.run(["rg", "--version"], capture_output=True, timeout=1)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


async def _ripgrep_search(
    pattern: str,
    search_path: Path,
    file_pattern: str,
    ignore_case: bool,
    context_lines: int,
    max_results: int,
    timeout_seconds: float = 10.0,
    *,
    literal: bool = False,
) -> list[dict[str, str | int]]:
    """Execute search using ripgrep (fastest tier). Returns raw match list."""
    search_root = search_path if search_path.is_dir() else search_path.parent
    cmd = ["rg", "--json", *rg_traversal_args(search_root)]

    if literal:
        cmd.append("--fixed-strings")

    if ignore_case:
        cmd.append("--ignore-case")

    if context_lines > 0:
        cmd.extend(["-C", str(context_lines)])

    # ``--glob`` overrides ignore filters for whatever it matches, so a match-all spelling (``*``, ``**``)
    # must not be passed or it would pull in ignored trees.
    if not is_match_all(file_pattern):
        cmd.extend(["--glob", normalize_glob(file_pattern)])

    cmd.extend(["--", pattern, str(search_path)])

    results: list[dict[str, str | int]] = []
    match_count = 0

    def _collect(line_bytes: bytes) -> bool:
        nonlocal match_count
        try:
            data = json.loads(line_bytes)
            if data.get("type") not in ("match", "context"):
                return False
            line_type = data["type"]
            results.append(
                {
                    "file": data["data"]["path"]["text"],
                    "line": data["data"]["line_number"],
                    "content": data["data"]["lines"]["text"].rstrip("\n"),
                    "type": line_type,
                }
            )
        except (ValueError, KeyError):
            return False
        if line_type != "match":
            return False
        match_count += 1
        return match_count >= max_results

    try:
        outcome = await run_rg(
            cmd,
            cwd=search_root,
            timeout_seconds=timeout_seconds,
            on_line=_collect,
        )
        if outcome.failed:
            logger.warning(f"ripgrep error: {outcome.stderr}")
            # An unreadable directory fails the run but leaves valid matches; a pattern ripgrep cannot parse
            # leaves none, and the Python tier (look-around, back-references) may still be able to search it.
            if not results:
                raise RuntimeError("ripgrep failed")
    except (TimeoutError, RuntimeError) as e:
        logger.warning(f"ripgrep search failed: {e}, falling back to Python")
        raise

    return results


class GrepInput(BaseModel):
    """Grep 工具输入参数"""

    pattern: str = Field(description="搜索模式（支持正则表达式）")
    path: str = Field(default=".", description="搜索路径（默认当前目录）")
    file_pattern: str = Field(default="**/*", description="文件匹配模式（默认所有文件）")
    ignore_case: bool = Field(default=False, description="是否忽略大小写（默认 False）")
    literal: bool = Field(
        default=False,
        description="精确匹配模式：当 pattern 包含特殊字符（如 .()[]{}$^|*+?\\）时使用，跳过正则解析直接匹配文本",
    )
    context_lines: int = Field(default=0, ge=0, le=10, description="匹配行前后的上下文行数（默认 0，最大 10）")


def resolve_grep_tool_description(
    io_cfg: FileIOConfig,
    locale: str | None = None,
) -> str:
    """Resolve LLM-facing grep_tool description."""
    if is_chinese(locale):
        return f"""搜索文件内容。Output: one line per match as 'path:line_number: content'.

参数：
- pattern: 搜索模式（必需）
- path: 搜索路径（默认当前目录）
- file_pattern: 文件匹配模式（默认 **/*）
- ignore_case: 忽略大小写（默认 False）
- literal: 精确文本匹配（默认 False）。当 pattern 包含 .()[]{{}}$^|*+?\\ 等特殊字符时使用，无需转义
- context_lines: 匹配行前后的上下文行数（默认 0，最大 10）

示例：
- 查找函数定义：grep_tool(pattern="def main")
- 精确匹配含特殊字符的文本：grep_tool(pattern="response.json()", literal=True)
- 正则搜索：grep_tool(pattern="class \\w+\\(.*\\):")
- 在 Python 文件中查找：grep_tool(pattern="TODO", file_pattern="**/*.py")

限制：最多 {io_cfg.max_search_results} 个结果，{io_cfg.max_search_files} 个文件，超时 {int(io_cfg.search_timeout_seconds)}s
"""
    return f"""Search file contents for matching text patterns. Output: one line per match as 'path:line_number: content'.

Parameters:
- pattern: Search pattern (regex or literal text when literal=True), required
- path: Search directory (default '.')
- file_pattern: File glob pattern (default '**/*')
- ignore_case: Ignore casing (default False)
- literal: Exact string matching (default False). Use when pattern contains special characters like .()[]{{}}$^|*+?\\ without escaping
- context_lines: Context lines before/after matches (default 0, max 10)

Examples:
- Find function definitions: grep_tool(pattern="def main")
- Exact match with special characters: grep_tool(pattern="response.json()", literal=True)
- Regex search: grep_tool(pattern="class \\w+\\(.*\\):")
- Search inside Python files: grep_tool(pattern="TODO", file_pattern="**/*.py")

Limits: at most {io_cfg.max_search_results} results, {io_cfg.max_search_files} files, timeout {int(io_cfg.search_timeout_seconds)}s
"""


def create_grep_tool(
    io_config: FileIOConfig | None = None,
    *,
    locale: str | None = None,
) -> BaseTool:
    """创建内容搜索工具

    从 context 动态获取 executor 进行路径解析。
    """
    io_cfg = io_config or DEFAULT_FILE_IO_CONFIG
    regex_validator = RegexValidator(io_cfg)

    tool_description = resolve_grep_tool_description(io_cfg, locale)

    @tool("grep_tool", description=tool_description, args_schema=GrepInput)
    async def grep_func(
        pattern: str,
        path: str = ".",
        file_pattern: str = "**/*",
        ignore_case: bool = False,
        literal: bool = False,
        context_lines: int = 0,
        *,
        config: RunnableConfig,  #  纯净设计：从 config 获取 context
    ) -> str:
        """搜索文件内容

        Args:
            pattern: 搜索模式（支持正则表达式，或 literal=True 时为精确文本）
            path: 搜索路径
            file_pattern: 文件匹配模式
            ignore_case: 是否忽略大小写
            literal: 精确文本匹配模式（跳过正则解析）
            context_lines: 匹配行前后的上下文行数
            config: LangChain 运行时配置（自动注入）

        Returns:
            匹配的行及其位置

        Raises:
            FileNotFoundError: 搜索路径不存在
            PermissionError: 权限不足
            ValueError: 路径不安全或参数错误
            ToolError: 正则表达式错误或安全问题
        """
        try:
            executor = ensure_executor(config)

            if (mcp_error := mcp_namespace_error(path)) is not None:
                raise ToolError(message=mcp_error, user_hint=mcp_error)

            try:
                search_path = await executor.resolve_path(path)
            except ValueError as e:
                raise ToolError(
                    message=f"Invalid path: {path} - {e}",
                    user_hint=f"The path '{path}' is invalid or outside the workspace.",
                ) from e

            search_path_obj = Path(search_path)
            disabled_roots = get_disabled_skill_roots(config)

            if disabled_roots and is_under_disabled_skill_root(str(search_path_obj), disabled_roots):
                raise ToolError(
                    message=f"Path blocked: {path}",
                    user_hint="This path belongs to a disabled skill and cannot be searched.",
                )

            # 验证路径存在
            if not search_path_obj.exists():
                suggestions = suggest_similar_paths(search_path)
                raise ToolError(
                    message=f"Path not found: {path}",
                    user_hint=format_path_not_found_hint(path, suggestions),
                )

            if not pattern.strip():
                raise ToolError(
                    message="Empty search pattern",
                    user_hint="Please provide a non-empty search pattern.",
                )

            flags = re.IGNORECASE if ignore_case else 0
            if literal:
                regex = re.compile(re.escape(pattern), flags)
            else:
                regex = regex_validator.validate_and_compile(pattern, flags)

            try:
                compile_glob(file_pattern)
            except ValueError as e:
                raise ToolError(
                    message=f"Invalid file pattern '{file_pattern}': {e}",
                    user_hint=f"The file pattern '{file_pattern}' is invalid. Use patterns like '*.py', '**/*.js', etc.",
                ) from e

            if io_cfg.enable_audit_log:
                logger.info(
                    f"SECURITY AUDIT: grep_tool - pattern={pattern}, path={path}, "
                    f"file_pattern={file_pattern}, ignore_case={ignore_case}, literal={literal}"
                )

            # --- Search phase: collect raw results from ripgrep or Python fallback ---
            results: list[dict[str, str | int]] = []
            files_searched = 0
            used_ripgrep = False

            if _has_ripgrep():
                try:
                    results = await _ripgrep_search(
                        pattern,
                        search_path_obj,
                        file_pattern,
                        ignore_case,
                        context_lines,
                        io_cfg.max_search_results,
                        io_cfg.search_timeout_seconds,
                        literal=literal,
                    )
                    used_ripgrep = True
                except Exception as e:
                    logger.debug(f"ripgrep fallback: {e}")

            if not used_ripgrep:
                files = await asyncio.to_thread(
                    collect_candidate_files,
                    search_root=search_path_obj,
                    file_pattern=file_pattern,
                    max_files=io_cfg.max_search_files,
                    include_ignored=False,
                )
                results, files_searched = await search_files(
                    files,
                    regex,
                    search_path_obj,
                    regex_validator=regex_validator,
                    max_results=io_cfg.max_search_results,
                    timeout_seconds=io_cfg.search_timeout_seconds,
                )

            # --- Format phase ---
            if disabled_roots and results:
                filtered_results: list[dict[str, str | int]] = []
                for match in results:
                    rel_file = str(match.get("file", ""))
                    abs_file = str(search_path_obj / rel_file) if rel_file else str(search_path_obj)
                    if not is_under_disabled_skill_root(abs_file, disabled_roots):
                        filtered_results.append(match)
                results = filtered_results

            if used_ripgrep:
                files_searched = len({str(r["file"]) for r in results})

            return format_grep_results(
                redact_matches(results),
                redact_sensitive_text(pattern),
                files_searched,
                io_cfg.max_search_results,
                is_regex=not literal,
            )

        except ToolError:
            # ToolError 已经包含友好提示，直接传播
            raise
        except Exception as e:
            # 未预期的错误，包装成 ToolError
            logger.exception(f"Unexpected error in grep_tool: {e}")
            raise ToolError(
                message=f"Unexpected error during content search: {e}",
                user_hint="An unexpected error occurred. Please check the search parameters and try again.",
            ) from e

    return grep_func
