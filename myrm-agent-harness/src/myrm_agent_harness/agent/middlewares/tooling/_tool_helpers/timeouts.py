"""[INPUT]
- （无跨模块依赖）

[OUTPUT]
- get_tool_timeout: 按工具名与参数推导默认超时

[POS]
`_tool_helpers/` 的超时策略；只读工具名与参数。
"""

from __future__ import annotations


def get_tool_timeout(tool_name: str, tool_args: dict[str, object] | None = None) -> float:
    """Get timeout for tool based on name pattern matching (zero-config).

    When a tool's input schema declares an explicit ``timeout`` argument (e.g.
    ``bash_code_execute_tool``), the caller supplies ``tool_args`` so the executor
    honors it for long-running commands instead of silently killing them at the
    zero-config default.

    Returns:
        Timeout in seconds: 300s for media generation, 120s for shell/browser/mcp,
        30s for file I/O, 60s default. An explicit ``tool_args["timeout"]`` on
        shell/browser/mcp floats the floor up to it (clamped to 600s, matching the
        ``BashInput.timeout`` max).
    """
    base = 60.0
    if tool_name.startswith(("image_tool", "video_tool")):
        base = 300.0
    elif tool_name.startswith(("bash", "browser", "mcp_")):
        base = 120.0
    elif tool_name.startswith(("file_read", "file_write", "file_edit", "glob", "grep")):
        base = 30.0

    explicit = tool_args and tool_args.get("timeout")
    if (
        tool_name.startswith(("bash", "browser", "mcp_"))
        and isinstance(explicit, int)
        and not isinstance(explicit, bool)
        and explicit > 0
    ):
        return min(float(explicit), 600.0)
    return base
