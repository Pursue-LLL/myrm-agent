"""
[INPUT]
myrm_agent_harness.agent.security.path_security (POS: 路径安全校验)
myrm_agent_harness.toolkits.file_parsers (POS: Office 文档解析器)
myrm_agent_harness.toolkits.web_fetch.engine::CrawlEngine (POS: 分层爬虫引擎)

[OUTPUT]
_build_mention_reference_context: 读取结构化 @ 引用并构建注入上下文
_inject_mentioned_files_into_query: 将上下文追加到用户查询
_build_codebase_overview: 轻量扫描工作区文件统计（@codebase）
_codebase_overview_part: 构建 @codebase XML 注入片段
_read_file_lines: 读取文件的指定行范围
_get_git_staged_diff: 获取 Git staged diff
_get_folder_tree: 获取文件夹树结构
_fetch_url_content: 获取 URL 内容

[POS]
上下文富引用预处理器。支持结构化 workspace/uploaded/generated/git/url 引用，
并转换为安全的 XML 上下文字符串。
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from .models import MentionReferenceRequest, MultimodalQuery

logger = logging.getLogger(__name__)

_MENTION_MAX_FILES = 10
_LINE_RANGE_PATTERN = re.compile(r"^(.+?):(\d+)(?:-(\d+))?$")
_MENTION_MAX_INLINE_BYTES = 100 * 1024  # 100KB per file
_MENTION_MAX_TOTAL_BYTES = 500 * 1024  # 500KB total
_DOCUMENT_EXTENSIONS = {".docx", ".xlsx", ".xls", ".pptx", ".ppt"}
_BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".ico",
    ".mp3",
    ".mp4",
    ".avi",
    ".mov",
    ".zip",
    ".tar",
    ".gz",
    ".exe",
    ".dll",
    ".so",
    ".bin",
    ".pdf",
}
_FOLDER_TREE_MAX_ENTRIES = 200
_FOLDER_TREE_EXCLUDED_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache", ".mypy_cache"}
_CODEBASE_SCAN_EXCLUDED_DIRS = _FOLDER_TREE_EXCLUDED_DIRS | {".myrm", "dist", "build", ".next", "target", "coverage"}
_CODEBASE_SCAN_MAX_FILES = 10_000
_URL_FETCH_TIMEOUT = 30


def _read_file_lines(file_path: str, start_line: int | None, end_line: int | None) -> str:
    """Read specific lines from a file.

    Args:
        file_path: Absolute path to the file
        start_line: Starting line number (1-indexed), None for full file
        end_line: Ending line number (1-indexed, inclusive), None for full file

    Returns:
        File content or specified line range
    """
    with open(file_path, encoding="utf-8", errors="replace") as f:
        if start_line is None:
            return f.read()

        lines = f.readlines()
        total_lines = len(lines)

        start_idx = max(0, start_line - 1)
        end_idx = min(total_lines, end_line) if end_line else total_lines

        return "".join(lines[start_idx:end_idx])


def _text_reference_to_structured(ref: str) -> MentionReferenceRequest:
    if ref == "@staged":
        return MentionReferenceRequest(type="git_staged", label="@staged")
    if ref == "@diff":
        return MentionReferenceRequest(type="git_diff", label="@diff")
    if ref == "@codebase":
        return MentionReferenceRequest(type="codebase", label="@codebase")
    if ref.startswith("@folder:"):
        path = ref.removeprefix("@folder:")
        return MentionReferenceRequest(type="workspace_folder", path=path or ".", label=ref)
    if ref.startswith("@url:"):
        url = ref.removeprefix("@url:")
        return MentionReferenceRequest(type="url", url=url, label=ref)

    match = _LINE_RANGE_PATTERN.match(ref)
    if match:
        path, start_raw, end_raw = match.groups()
        start_line = int(start_raw)
        end_line = int(end_raw) if end_raw else start_line
        if end_line < start_line:
            start_line, end_line = end_line, start_line
        return MentionReferenceRequest(
            type="workspace_file",
            path=path,
            label=ref,
            start_line=start_line,
            end_line=end_line,
        )
    return MentionReferenceRequest(type="workspace_file", path=ref, label=ref)


async def _build_mentioned_file_context(
    mentioned_files: list[str],
    workspace_dir: str,
    max_context_tokens: int | None = None,
) -> tuple[str, list[str], int]:
    structured = [_text_reference_to_structured(ref) for ref in mentioned_files]
    return await _build_mention_reference_context(structured, workspace_dir, max_context_tokens)


def _get_git_staged_diff(workspace_dir: str) -> str:
    """Get git staged diff (git diff --cached) for current workspace.

    Returns empty string if not a git repo, or if no staged changes, or on error.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--cached"],
            cwd=workspace_dir,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        logger.debug("git diff --cached returned %d: %s", result.returncode, result.stderr)
    except subprocess.TimeoutExpired:
        logger.warning("git diff --cached timeout (30s) in %s", workspace_dir)
    except FileNotFoundError:
        logger.debug("git command not found")
    except Exception as e:
        logger.debug("Failed to get git staged diff: %s", e)
    return ""


def _get_folder_tree(abs_path: str, workspace_dir: str) -> str:
    """Generate folder tree structure (limited to _FOLDER_TREE_MAX_ENTRIES).

    Filters out common excluded directories like .git, node_modules, __pycache__.
    Returns empty string if path doesn't exist or is not a directory.
    """
    if not os.path.exists(abs_path) or not os.path.isdir(abs_path):
        return ""

    lines: list[str] = []
    total_entries = 0

    try:
        for root, dirs, files in os.walk(abs_path):
            dirs[:] = [d for d in dirs if d not in _FOLDER_TREE_EXCLUDED_DIRS]

            rel_root = os.path.relpath(root, workspace_dir)
            if rel_root == ".":
                rel_root = ""

            for d in sorted(dirs):
                if total_entries >= _FOLDER_TREE_MAX_ENTRIES:
                    lines.append("... (truncated)")
                    return "\n".join(lines)
                dir_path = os.path.join(rel_root, d) if rel_root else d
                lines.append(f"- {dir_path}/")
                total_entries += 1

            for f in sorted(files):
                if total_entries >= _FOLDER_TREE_MAX_ENTRIES:
                    lines.append("... (truncated)")
                    return "\n".join(lines)
                if not f.startswith("."):
                    file_path = os.path.join(rel_root, f) if rel_root else f
                    lines.append(f"- {file_path}")
                    total_entries += 1
    except Exception as e:
        logger.warning("Failed to generate folder tree for %s: %s", abs_path, e)
        return ""

    return "\n".join(lines)


async def _fetch_url_content(url: str) -> str:
    """Fetch URL content using CrawlEngine.

    Returns empty string on error or if URL is blocked by SSRF protection.
    """
    try:
        from myrm_agent_harness.toolkits.web_fetch.engine import CrawlEngine

        engine = CrawlEngine()
        doc = await engine.crawl(url)
        if doc and doc.page_content:
            return doc.page_content.strip()
    except Exception as e:
        logger.warning("Failed to fetch URL %s: %s", url, e)
    return ""


async def _build_mention_reference_context(
    mention_references: list[MentionReferenceRequest],
    workspace_dir: str,
    max_context_tokens: int | None = None,
) -> tuple[str, list[str], int]:
    """Read structured GUI @ references and build prompt context."""

    from myrm_agent_harness.agent.security.path_security import (
        is_dangerous_path,
        is_sensitive_file,
        safe_join_path,
    )
    from myrm_agent_harness.utils.text_utils import get_token_count

    workspace_real = str(Path(workspace_dir).expanduser().resolve())
    parts: list[str] = []
    total_bytes = 0
    total_tokens = 0
    warnings: list[str] = []

    # Token budget limits (25% soft, 50% hard)
    soft_limit = int(max_context_tokens * 0.25) if max_context_tokens else 999_999_999
    hard_limit = int(max_context_tokens * 0.50) if max_context_tokens else 999_999_999

    for ref in mention_references[:_MENTION_MAX_FILES]:
        if ref.type == "git_staged":
            diff_content = _get_git_staged_diff(workspace_real)
            if diff_content:
                diff_bytes = len(diff_content.encode("utf-8"))
                if total_bytes + diff_bytes <= _MENTION_MAX_TOTAL_BYTES:
                    parts.append(_xml_part("@staged", "git-diff", diff_content))
                    total_bytes += diff_bytes
                else:
                    parts.append(_xml_metadata("@staged", "git-diff", f"Diff too large ({_format_size(diff_bytes)})"))
            else:
                parts.append('<mentioned_file path="@staged" type="git-diff">No staged changes</mentioned_file>')
            continue

        if ref.type == "git_diff":
            try:
                result = subprocess.run(
                    ["git", "diff"],
                    cwd=workspace_real,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                if result.returncode == 0 and result.stdout.strip():
                    diff_content = result.stdout.strip()
                    diff_bytes = len(diff_content.encode("utf-8"))
                    if total_bytes + diff_bytes <= _MENTION_MAX_TOTAL_BYTES:
                        parts.append(_xml_part("@diff", "git-diff", diff_content))
                        total_bytes += diff_bytes
                    else:
                        parts.append(_xml_metadata("@diff", "git-diff", f"Diff too large ({_format_size(diff_bytes)})"))
                else:
                    parts.append('<mentioned_file path="@diff" type="git-diff">No unstaged changes</mentioned_file>')
            except Exception as e:
                logger.debug("Failed to get git diff: %s", e)
                parts.append('<mentioned_file path="@diff" error="git diff failed"/>')
            continue

        if ref.type == "workspace_folder":
            rel_path = ref.path or "."
            display_path = ref.label or f"@folder:{rel_path}"
            try:
                abs_folder = safe_join_path(workspace_real, rel_path)
            except ValueError:
                parts.append(_xml_error(display_path, "path outside workspace"))
                continue
            abs_folder_str = str(abs_folder)
            if is_dangerous_path(abs_folder_str) or is_sensitive_file(abs_folder_str):
                parts.append(_xml_error(display_path, "access denied"))
                continue

            tree_content = _get_folder_tree(abs_folder_str, workspace_real)
            if tree_content:
                tree_bytes = len(tree_content.encode("utf-8"))
                if total_bytes + tree_bytes <= _MENTION_MAX_TOTAL_BYTES:
                    parts.append(_xml_part(display_path, "folder-tree", tree_content))
                    total_bytes += tree_bytes
                else:
                    parts.append(_xml_metadata(display_path, "folder-tree", f"Tree too large ({_format_size(tree_bytes)})"))
            else:
                parts.append(_xml_error(display_path, "folder not found or empty"))
            continue

        if ref.type == "url":
            url = ref.url or ref.path or ""
            display_path = ref.label or f"@url:{url}"
            url_content = await _fetch_url_content(url)
            if url_content:
                url_bytes = len(url_content.encode("utf-8"))
                if total_bytes + url_bytes <= _MENTION_MAX_TOTAL_BYTES:
                    parts.append(_xml_part(display_path, "url", url_content))
                    total_bytes += url_bytes
                else:
                    parts.append(_xml_metadata(display_path, "url", f"Content too large ({_format_size(url_bytes)})"))
            else:
                parts.append(_xml_error(display_path, "failed to fetch URL"))
            continue

        if ref.type == "workspace_file":
            rel_path = ref.path
            if not rel_path:
                parts.append(_xml_error(ref.label or "@file", "missing path"))
                continue
            try:
                abs_path = safe_join_path(workspace_real, rel_path)
            except ValueError:
                parts.append(_xml_error(ref.label or rel_path, "path outside workspace"))
                continue
            display_path = ref.label or rel_path
            part, consumed_bytes = _workspace_file_part(
                str(abs_path),
                display_path,
                ref.start_line,
                ref.end_line,
                total_bytes,
            )
            parts.append(part)
            total_bytes += consumed_bytes
            continue

        if ref.type in ("uploaded_file", "generated_file"):
            part, consumed_bytes = await _stored_file_part(ref, total_bytes)
            parts.append(part)
            total_bytes += consumed_bytes
            continue

        if ref.type == "codebase":
            codebase_part, codebase_bytes = await _codebase_overview_part(workspace_real, total_bytes)
            parts.append(codebase_part)
            total_bytes += codebase_bytes
            continue

        parts.append(_xml_error(ref.label or ref.type, "unsupported reference"))

    if not parts:
        return "", [], 0

    # Calculate total tokens
    final_content = "\n\n<mentioned_files>\n" + "\n".join(parts) + "\n</mentioned_files>"
    total_tokens = get_token_count(final_content)

    # Check budget limits
    if total_tokens > hard_limit:
        warnings.append(
            f"Context size {total_tokens} tokens exceeds 50% limit ({hard_limit} tokens), some references may have been truncated"
        )
    elif total_tokens > soft_limit:
        warnings.append(f"Warning: Context size {total_tokens} tokens exceeds 25% soft limit ({soft_limit} tokens)")

    return final_content, warnings, total_tokens


def _workspace_file_part(
    abs_path: str,
    display_path: str,
    start_line: int | None,
    end_line: int | None,
    current_total_bytes: int,
) -> tuple[str, int]:
    from myrm_agent_harness.agent.security.path_security import is_dangerous_path, is_sensitive_file

    if is_dangerous_path(abs_path) or is_sensitive_file(abs_path):
        return _xml_error(display_path, "access denied"), 0
    if not os.path.isfile(abs_path):
        return _xml_error(display_path, "file not found"), 0

    ext = Path(abs_path).suffix.lower()
    try:
        file_size = os.path.getsize(abs_path)
    except OSError:
        file_size = 0

    if ext in _BINARY_EXTENSIONS:
        return (
            _xml_metadata(
                display_path,
                "binary",
                f"Binary file ({_format_size(file_size)}), use file_read_tool to inspect if needed.",
            ),
            0,
        )

    if ext in _DOCUMENT_EXTENSIONS:
        if start_line is not None:
            return _xml_error(display_path, "line range not supported for Office documents"), 0
        content = _parse_document(abs_path, ext)
        if content:
            content_bytes = len(content.encode("utf-8"))
            if _can_inline(content_bytes, current_total_bytes):
                return _xml_part(display_path, "document", content), content_bytes
        return _xml_metadata(display_path, "document", f"Document too large ({_format_size(file_size)})"), 0

    try:
        content = _read_file_lines(abs_path, start_line, end_line)
    except Exception as exc:
        logger.warning("Failed to read mentioned file %s: %s", display_path, exc)
        return _xml_error(display_path, "read failed"), 0

    content_bytes = len(content.encode("utf-8"))
    if _can_inline(content_bytes, current_total_bytes):
        line_range = f" lines {start_line}-{end_line or start_line}" if start_line else ""
        return _xml_part(display_path, f"text{line_range}", content), content_bytes
    return _xml_metadata(display_path, "text", f"Content too large to inline ({_format_size(content_bytes)})"), 0


async def _stored_file_part(ref: MentionReferenceRequest, current_total_bytes: int) -> tuple[str, int]:
    from app.core.storage import files_service

    if not ref.file_id:
        return _xml_error(ref.label or ref.type, "missing file_id"), 0

    file = await files_service.get_file_by_id(ref.file_id)
    if file is None:
        return _xml_error(ref.label or ref.file_id, "file not found"), 0

    content = await files_service.get_file_content_by_path(file.storage_path)
    display_path = ref.label or file.filename
    if content is None:
        return _xml_error(display_path, "file content not found"), 0

    ext = Path(file.filename).suffix.lower()
    if ext in _DOCUMENT_EXTENSIONS or ext == ".pdf":
        parsed = await _parse_stored_document(content, ext, file.filename)
        if parsed:
            parsed_bytes = len(parsed.encode("utf-8"))
            if _can_inline(parsed_bytes, current_total_bytes):
                return _xml_part(display_path, "document", parsed), parsed_bytes
        return _xml_metadata(display_path, "document", f"Document too large ({_format_size(file.size)})"), 0

    if ext in _BINARY_EXTENSIONS:
        return (
            _xml_metadata(
                display_path,
                "binary",
                f"Binary file ({_format_size(file.size)}), use file_read_tool to inspect if needed.",
            ),
            0,
        )

    try:
        text = content.decode("utf-8", errors="replace")
    except Exception:
        return _xml_metadata(display_path, "binary", f"Binary file ({_format_size(file.size)})"), 0

    text_bytes = len(text.encode("utf-8"))
    if _can_inline(text_bytes, current_total_bytes):
        return _xml_part(display_path, "stored-text", text), text_bytes
    return _xml_metadata(display_path, "stored-text", f"Content too large to inline ({_format_size(text_bytes)})"), 0


async def _parse_stored_document(content: bytes, ext: str, filename: str) -> str | None:
    suffix = ext if ext else Path(filename).suffix.lower()
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp:
            temp.write(content)
            temp_path = temp.name
        if suffix == ".pdf":
            from myrm_agent_harness.toolkits.file_parsers import PDFPlumberParser

            return await PDFPlumberParser(extract_tables=True, parallel=False).parse(temp_path)
        return _parse_document(temp_path, suffix)
    except Exception as exc:
        logger.warning("Failed to parse stored document %s: %s", filename, exc)
        return None
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def _parse_document(path: str, ext: str) -> str | None:
    """Parse Office document to text using Harness parsers (sync)."""
    try:
        if ext == ".docx":
            from myrm_agent_harness.toolkits.file_parsers import DocxParser

            return DocxParser()._parse_sync(path)
        if ext in (".xlsx", ".xls"):
            from myrm_agent_harness.toolkits.file_parsers import ExcelParser

            return ExcelParser()._parse_sync(path)
        if ext in (".pptx", ".ppt"):
            from myrm_agent_harness.toolkits.file_parsers import PptxParser

            return PptxParser()._parse_sync(path)
    except Exception as e:
        logger.warning("Failed to parse document %s: %s", path, e)
    return None


def _build_codebase_overview(workspace_path: Path) -> str:
    """Lightweight workspace scan for @codebase mention (no index DB)."""
    file_count = 0
    ext_counts: dict[str, int] = {}
    truncated = False

    for dirpath, dirnames, filenames in os.walk(workspace_path):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in _CODEBASE_SCAN_EXCLUDED_DIRS and not name.startswith(".")
        ]
        for filename in filenames:
            if filename.startswith("."):
                continue
            file_count += 1
            ext = Path(filename).suffix.lower() or "(no ext)"
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
            if file_count >= _CODEBASE_SCAN_MAX_FILES:
                truncated = True
                break
        if truncated:
            break

    overview_parts = [f"Codebase Overview: {file_count} files"]
    if truncated:
        overview_parts.append(f"(scan capped at {_CODEBASE_SCAN_MAX_FILES} files)")
    if ext_counts:
        ext_summary = ", ".join(
            f"{ext}: {count}" for ext, count in sorted(ext_counts.items(), key=lambda item: (-item[1], item[0]))[:10]
        )
        overview_parts.append(f"Extensions: {ext_summary}")
    overview_parts.append("Use grep_tool / glob_tool for code exploration.")
    return "\n".join(overview_parts)


async def _codebase_overview_part(workspace_dir: str, current_total_bytes: int) -> tuple[str, int]:
    """Build a lightweight codebase overview for @codebase mention."""
    workspace_path = Path(workspace_dir)
    if not workspace_path.is_dir():
        return _xml_metadata("@codebase", "codebase-overview", "Workspace unavailable"), 0

    overview = await asyncio.to_thread(_build_codebase_overview, workspace_path)
    overview_bytes = len(overview.encode("utf-8"))
    if _can_inline(overview_bytes, current_total_bytes):
        return _xml_part("@codebase", "codebase-overview", overview), overview_bytes
    return _xml_metadata("@codebase", "codebase-overview", overview.split("\n", maxsplit=1)[0]), 0


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes}B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    return f"{size_bytes / (1024 * 1024):.1f}MB"


def _can_inline(content_bytes: int, current_total_bytes: int) -> bool:
    return content_bytes <= _MENTION_MAX_INLINE_BYTES and current_total_bytes + content_bytes <= _MENTION_MAX_TOTAL_BYTES


def _xml_part(path: str, part_type: str, content: str) -> str:
    return f"<mentioned_file path={quoteattr(path)} type={quoteattr(part_type)}>\n{escape(content)}\n</mentioned_file>"


def _xml_metadata(path: str, part_type: str, message: str) -> str:
    return f"<mentioned_file path={quoteattr(path)} type={quoteattr(part_type)}>{escape(message)}</mentioned_file>"


def _xml_error(path: str, message: str) -> str:
    return f"<mentioned_file path={quoteattr(path)} error={quoteattr(message)}/>"


def _inject_mentioned_files_into_query(
    query: MultimodalQuery,
    context: str,
) -> MultimodalQuery:
    """Append mentioned file context to the user query."""
    if not context:
        return query
    if isinstance(query, str):
        return query + context
    for part in query:
        if part.get("type") == "text" and isinstance(part.get("text"), str):
            part["text"] = str(part["text"]) + context
            return query
    query.append({"type": "text", "text": context})
    return query
