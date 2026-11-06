"""内容搜索工具（Claude Code 兼容）

[INPUT]
- langchain.tools::tool (POS: LangChain 工具装饰器)
- pydantic::BaseModel, Field (POS: 参数验证)
- agent.config.file_io::FileIOConfig (POS: I/O 配置)
- agent.security.redact::redact_sensitive_text (POS: 工具输出脱敏，防止凭证泄露到 LLM 上下文)
- core.security.path::is_sensitive_file (POS: 敏感文件模式的唯一来源)
- utils.errors::ToolError (POS: Framework-level error handling: ToolError with the format_for_llm protocol, and ModelOutputValidator)
- utils.locale::is_chinese (POS: Shared locale utilities, single source of truth for locale string handling)
- _redaction::redact_matches (POS: 逐文件按类型脱敏匹配行，源码里含 token 的类型名/变量名不被误遮)
- agent.meta_tools._context_recovery::ensure_executor (POS: Executor ContextVar recovery)
- regex_validator::RegexValidator (POS: 正则表达式验证器，防止 ReDoS)
- _formatter::format_grep_results (POS: Grep output formatter: path-grouped output from 5 matches on, line truncation, non-code file capping)
- fallback_discovery::collect_candidate_files (POS: 候选文件发现策略：Python 档发现)
- fallback_search::search_files, SearchOutcome (POS: Python 档内容搜索：按 ripgrep 的行语义匹配并带上下文行，mmap 扫描、分批并发、结果与时间上限)
- rg_matches::RgMatches (POS: ripgrep --json 事件流收集为匹配行；目录级搜索不返回敏感文件内容)
- rg_traversal::rg_traversal_args (POS: ripgrep 档遍历策略，与 Python 档遵循同一套选文件策略)
- glob_match::compile_glob, is_match_all, normalize_glob (POS: 两档共用的 glob 语义：锚定、**、花括号)
- _rg_runner::run_rg (POS: ripgrep 子进程生命周期：提前终止、超时回收)
- path_hint::format_path_not_found_hint, mcp_namespace_error, suggest_similar_paths (POS: File-search and file-ops UX helper for mistyped, Unicode-decomposed, or moved workspace paths)
- skill_path_filter::get_disabled_skill_roots, is_under_disabled_skill_root (POS: ACL filter preventing file tools from reading disabled skill directories)

[OUTPUT]
- GrepInput: Grep 工具输入参数模型
- create_grep_tool: 创建 Grep 工具的工厂函数

[POS]
Content search tool (Claude Code compatible). Searches file contents for matching text patterns
with regex and literal (--fixed-strings) modes, path-grouped output from 5 matches on and intelligent line truncation.
Two search tiers follow one file-selection policy (``rg_traversal`` for ripgrep, ``fallback_discovery`` for the
Python tier); ripgrep runs first, and the Python tier takes over when ripgrep is missing or gives no answer
(``RgRunResult.answered``). A search over a directory withholds the lines of sensitive files on both tiers.

"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from langchain.tools import tool
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from myrm_agent_harness.agent.config import DEFAULT_FILE_IO_CONFIG, FileIOConfig
from myrm_agent_harness.agent.meta_tools._context_recovery import ensure_executor
from myrm_agent_harness.agent.security.redact import redact_sensitive_text
from myrm_agent_harness.core.security.path import is_sensitive_file
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
from .rg_matches import RgMatches
from .rg_traversal import rg_traversal_args
from .skill_path_filter import get_disabled_skill_roots, is_under_disabled_skill_root

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


def _has_ripgrep() -> bool:
    """True while ``rg`` is on PATH, looked up on every call so one installed later is used at once.

    A ripgrep that cannot start (``run_rg`` raises) or gave no answer (``RgRunResult.require_answer`` raises) does
    not end the call: both tools catch the error and hand the search to the Python tier.
    """
    return shutil.which("rg") is not None


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
) -> RgMatches:
    """Execute search using ripgrep (fastest tier). Returns the rows it found.

    Raises:
        RuntimeError: ripgrep gave no answer (``RgRunResult.answered``), so the Python tier must search. A failure
            after output (an unreadable directory) stands, even when nothing matched.
    """
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

    # Naming a sensitive file as the path is a deliberate read (approval-gated); walking a directory is not.
    matches = RgMatches(max_results, withhold_sensitive=search_path.is_dir())

    outcome = await run_rg(
        cmd,
        cwd=search_root,
        timeout_seconds=timeout_seconds,
        on_line=matches.feed,
    )
    # An unreadable directory fails the run after ripgrep searched on, so what it printed stands, no match
    # included; a pattern it cannot parse fails before it prints, and the Python tier (look-around,
    # back-references) may still be able to search it. A killed or crashed run vouches for nothing.
    outcome.require_answer()

    return matches


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

            # Rows name a file relative to the directory searched; a single file is named by its own name.
            search_root = search_path_obj if search_path_obj.is_dir() else search_path_obj.parent

            # --- Search phase: collect raw results from ripgrep or Python fallback ---
            found: RgMatches | None = None
            if _has_ripgrep():
                try:
                    found = await _ripgrep_search(
                        pattern,
                        search_path_obj,
                        file_pattern,
                        ignore_case,
                        context_lines,
                        io_cfg.max_search_results,
                        io_cfg.search_timeout_seconds,
                        literal=literal,
                    )
                except Exception as e:
                    logger.warning(f"ripgrep search error: {e!r}, falling back to Python")

            # Only the Python tier knows how many files it searched; ripgrep's own count is wrong before version 15.
            files_searched: int | None = None
            scan_limit: int | None = None
            timed_out = False
            if found is not None:
                results = found.rows
            else:
                # One candidate beyond the cap shows whether the cap cut the scan short.
                candidates = await asyncio.to_thread(
                    collect_candidate_files,
                    search_root=search_path_obj,
                    file_pattern=file_pattern,
                    max_files=io_cfg.max_search_files + 1,
                    include_ignored=False,
                )
                if len(candidates) > io_cfg.max_search_files:
                    scan_limit = io_cfg.max_search_files
                files = candidates[: io_cfg.max_search_files]
                if search_path_obj.is_dir():
                    files = [candidate for candidate in files if not is_sensitive_file(str(candidate))]
                outcome = await search_files(
                    files,
                    regex,
                    search_root,
                    regex_validator=regex_validator,
                    max_results=io_cfg.max_search_results,
                    timeout_seconds=io_cfg.search_timeout_seconds,
                    context_lines=context_lines,
                )
                results = outcome.rows
                files_searched = outcome.files_searched
                timed_out = outcome.timed_out

            # --- Format phase ---
            if disabled_roots and results:
                filtered_results: list[dict[str, str | int]] = []
                for match in results:
                    rel_file = str(match.get("file", ""))
                    abs_file = str(search_root / rel_file) if rel_file else str(search_root)
                    if not is_under_disabled_skill_root(abs_file, disabled_roots):
                        filtered_results.append(match)
                results = filtered_results

            return format_grep_results(
                redact_matches(results),
                redact_sensitive_text(pattern),
                files_searched,
                io_cfg.max_search_results,
                is_regex=not literal,
                scan_limit=scan_limit,
                timed_out=timed_out,
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
