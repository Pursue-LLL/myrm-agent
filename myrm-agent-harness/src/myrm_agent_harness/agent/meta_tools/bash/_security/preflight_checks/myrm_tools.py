"""阻止在 bash 中使用 myrm_tools：AST、sh -c、-m、管道与引用脚本扫描。

[POS]
bash 预检子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path

from myrm_agent_harness.agent.meta_tools.bash._security.shell_parse import extract_shell_c_payload
from myrm_agent_harness.core.security.redact import command_preview

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# myrm_tools guard (bash only; Dynamic Workflow inject_ptc is separate)
# ---------------------------------------------------------------------------

_SHELL_MYRM_TOOLS_IMPORT_RE = re.compile(
    r"(?:^|\n)\s*(?:import\s+myrm_tools\b|from\s+myrm_tools\s+import\b)",
    re.MULTILINE,
)

_PYTHON_SCRIPT_INVOCATION_RE = re.compile(
    r"(?:^|[\s;&|])python3?(?:\s+-[^\s]+)*\s+([^\s;&|]+\.py)\b",
    re.IGNORECASE | re.MULTILINE,
)

_PYTHON_M_MYRM_TOOLS_RE = re.compile(
    r"\bpython3?\s+(?:-[^\s]+\s+)*-m\s+myrm_tools(?:[.\s]|$)",
    re.IGNORECASE,
)

_MAX_REFERENCED_PY_SCAN_BYTES = 512 * 1024

_MYRM_TOOLS_BLOCK_MESSAGE = (
    "Command blocked: `import myrm_tools` is not available in bash_code_execute_tool. "
    "Use native tools for single calls; use `from skills.* import ...` "
    "for MCP batch scripts; persist cross-bash data under `/workspace` JSON files."
)
_MYRM_TOOLS_BLOCK_HINT = (
    "Do not use myrm_tools in bash. Single calls: native tools "
    "(file_read_tool, web_search_tool, …). MCP batch: from skills.* import …. "
    "Cross-bash data: write `/workspace` JSON (json.dump or file_write_tool). "
    "Long-script progress: MYRM_PROGRESS echo."
)


def _ast_root_name(node: ast.AST) -> str | None:
    current = node
    while isinstance(current, ast.Attribute):
        current = current.value
    if isinstance(current, ast.Name):
        return current.id
    return None


def _shell_command_references_myrm_tools(command: str) -> bool:
    if _SHELL_MYRM_TOOLS_IMPORT_RE.search(command):
        return True
    shell_c_payload = extract_shell_c_payload(command)
    if shell_c_payload is None:
        return False
    return _python_ast_references_myrm_tools(shell_c_payload) or bool(
        _SHELL_MYRM_TOOLS_IMPORT_RE.search(shell_c_payload)
    )


def _python_ast_references_myrm_tools(code: str) -> bool:
    """Return True when parsed Python references the ``myrm_tools`` namespace."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".", 1)[0] == "myrm_tools":
                    return True
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.split(".", 1)[0] == "myrm_tools":
                return True
        elif isinstance(node, ast.Attribute) and _ast_root_name(node) == "myrm_tools":
            return True
    return False


def _raise_myrm_tools_blocked(command: str) -> None:
    from myrm_agent_harness.agent.errors.tool_error_category import ToolErrorCategory
    from myrm_agent_harness.utils.errors import ToolError

    logger.warning("Blocked myrm_tools reference in bash command: %s", command_preview(command, 120))
    raise ToolError(
        _MYRM_TOOLS_BLOCK_MESSAGE,
        user_hint=_MYRM_TOOLS_BLOCK_HINT,
        error_code="MYRM_TOOLS_BLOCKED",
        diagnostic_info={"error_category": ToolErrorCategory.GUARDRAIL_BLOCKED.value},
    )


def _scan_python_file_path(script_path: Path, command: str) -> None:
    if not script_path.is_file():
        return
    if script_path.stat().st_size > _MAX_REFERENCED_PY_SCAN_BYTES:
        logger.warning(
            "Skipping myrm_tools scan for oversized script reference: %s",
            script_path,
        )
        return
    try:
        source = script_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Unable to read referenced python script %s: %s", script_path, exc)
        return
    if _python_ast_references_myrm_tools(source):
        _raise_myrm_tools_blocked(command)


def _command_runs_myrm_tools_module(command: str) -> bool:
    return _PYTHON_M_MYRM_TOOLS_RE.search(command) is not None


def _extract_referenced_python_scripts(command: str) -> list[str]:
    return list(dict.fromkeys(_PYTHON_SCRIPT_INVOCATION_RE.findall(command)))


def _resolve_referenced_python_path(script_ref: str, workspace_root: str | None) -> Path | None:
    from myrm_agent_harness.toolkits.code_execution.utils.workspace_path import (
        WorkspacePathResolver,
    )

    cleaned = script_ref.strip().strip("'\"")
    if not cleaned.endswith(".py"):
        return None

    if WorkspacePathResolver.is_container_path(cleaned):
        local_path = WorkspacePathResolver.to_local_path(cleaned, workspace_root)
        return local_path.resolve() if local_path is not None else None

    if cleaned.startswith("/"):
        if not workspace_root:
            return None
        candidate = Path(cleaned)
        if not candidate.is_absolute():
            return None
        resolved = candidate.resolve()
        root = Path(workspace_root).resolve()
        if root not in resolved.parents and resolved != root:
            return None
        return resolved

    if workspace_root:
        return (Path(workspace_root).resolve() / cleaned).resolve()

    container_path = f"/workspace/{cleaned.lstrip('./')}"
    local_path = WorkspacePathResolver.to_local_path(container_path, None)
    return local_path.resolve() if local_path is not None else None


def _scan_referenced_python_files(command: str, workspace_root: str | None) -> None:
    for script_ref in _extract_referenced_python_scripts(command):
        script_path = _resolve_referenced_python_path(script_ref, workspace_root)
        if script_path is None:
            continue
        _scan_python_file_path(script_path, command)


def _scan_cat_pipe_feeder_python_files(command: str, workspace_root: str | None) -> None:
    from myrm_agent_harness.toolkits.code_execution.python_extractor import (
        extract_cat_py_paths_from_pipe_feeders,
    )

    for script_ref in extract_cat_py_paths_from_pipe_feeders(command):
        script_path = _resolve_referenced_python_path(script_ref, workspace_root)
        if script_path is None:
            continue
        _scan_python_file_path(script_path, command)


def check_myrm_tools_import(command: str, *, workspace_root: str | None = None) -> None:
    """Block ``myrm_tools`` in bash — reserved for Dynamic Workflow inject_ptc only.

    Python snippets: AST inspects imports and attribute access.
    Shell commands: line-leading ``import`` / ``from myrm_tools import``, plus
    ``bash|sh -c '…'`` inline payloads, ``quoted | python3`` stdin payloads,
    ``python -m myrm_tools``, ``cat *.py | python3`` feeder scans,
    and ``python *.py`` references scan file AST.
    Incidental ``myrm_tools`` in ``echo``/``grep`` allowed.

    Raises:
        ToolError: If command references ``myrm_tools`` in an executable Python path.
    """
    from myrm_agent_harness.toolkits.code_execution.code_detector import (
        CodeType,
        code_detector,
    )

    detection = code_detector.detect(command)
    code = detection.extracted_code if detection.code_type == CodeType.PYTHON else command

    if _python_ast_references_myrm_tools(code):
        _raise_myrm_tools_blocked(command)
        return

    if _command_runs_myrm_tools_module(command):
        _raise_myrm_tools_blocked(command)
        return

    if detection.code_type == CodeType.BASH and _shell_command_references_myrm_tools(command):
        _raise_myrm_tools_blocked(command)
        return

    from myrm_agent_harness.toolkits.code_execution.python_extractor import (
        extract_python_from_pipe_stdin,
    )

    pipe_stdin_code = extract_python_from_pipe_stdin(command)
    if pipe_stdin_code is not None and _python_ast_references_myrm_tools(pipe_stdin_code):
        _raise_myrm_tools_blocked(command)
        return

    _scan_cat_pipe_feeder_python_files(command, workspace_root)
    _scan_referenced_python_files(command, workspace_root)
