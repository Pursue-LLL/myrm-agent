"""Feishu CardKit streaming dashboard and dynamic tool header state machine.

Provides real-time interactive card header and subtitle evolution for
agent lifecycle events (thinking -> tool execution -> streaming reply -> completion),
along with 300ms adaptive update throttling.

[INPUT]
- OutboundMessage, tool event descriptors, and card metadata.

[OUTPUT]
- DashboardState: Enum of card dashboard lifecycle states.
- ToolActionMeta: Dataclass recording tool execution state and timing.
- build_dynamic_dashboard_card: Build or update an interactive card with evolving header.
- DashboardStreamThrottler: 300ms adaptive streaming throttler with force-flush.

[POS]
Feishu CardKit streaming interactive dashboard and state machine.
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Literal

_CARD_CONFIG: dict[str, object] = {"wide_screen_mode": True, "enable_forward": True}

_TOOL_ICON_MAP: dict[str, tuple[str, str, str]] = {
    # tool_prefix/name -> (icon, display_title, template_color)
    "web_search": ("🔍", "正在检索网络文档...", "watchet"),
    "search": ("🔍", "正在搜索信息...", "watchet"),
    "browser": ("🌐", "正在浏览网页...", "watchet"),
    "web_fetch": ("🌐", "正在抓取网页内容...", "watchet"),
    "bash": ("💻", "正在执行沙箱命令...", "watchet"),
    "terminal": ("💻", "正在执行终端命令...", "watchet"),
    "python": ("🐍", "正在运行 Python 分析脚本...", "watchet"),
    "code_exec": ("💻", "正在执行代码...", "watchet"),
    "git": ("📦", "正在进行版本库操作...", "watchet"),
    "file_read": ("📄", "正在读取文件...", "watchet"),
    "file_write": ("📝", "正在写入文件...", "watchet"),
    "database": ("🗄️", "正在查询数据库...", "watchet"),
    "sql": ("🗄️", "正在执行 SQL 语句...", "watchet"),
}


class DashboardState(str, enum.Enum):
    """Lifecycle states of the streaming interactive dashboard."""

    THINKING = "thinking"
    TOOL_RUNNING = "tool_running"
    STREAMING = "streaming"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ToolActionMeta:
    """Metadata tracking a tool execution step."""

    tool_name: str
    args_summary: str = ""
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    status: Literal["running", "success", "failed"] = "running"

    @property
    def elapsed_seconds(self) -> float:
        """Elapsed time in seconds."""
        end = self.end_time if self.end_time is not None else time.time()
        return max(0.0, end - self.start_time)


def resolve_tool_header(tool_name: str, args_summary: str = "") -> tuple[str, str, str]:
    """Resolve icon, title, and color template for a tool action.

    Args:
        tool_name: Name of the executing tool.
        args_summary: Compact summary of arguments.

    Returns:
        (icon, display_title, template_color)
    """
    normalized = tool_name.lower().replace("-", "_")
    for key, val in _TOOL_ICON_MAP.items():
        if key in normalized:
            title = val[1]
            if args_summary:
                title = f"{val[0]} {val[1].rstrip('.')} ({args_summary})"
            else:
                title = f"{val[0]} {val[1]}"
            return val[0], title, val[2]

    # Default fallback for custom tools/MCP
    display = f"⚙️ 正在调用工具 {tool_name}..."
    if args_summary:
        display = f"⚙️ 正在调用 {tool_name} ({args_summary})"
    return "⚙️", display, "watchet"


def build_dashboard_header(
    state: DashboardState,
    *,
    tool_meta: ToolActionMeta | None = None,
    custom_title: str = "",
    subtitle: str = "",
) -> dict[str, object]:
    """Build dynamic header dictionary for Feishu Interactive Card.

    Args:
        state: Current lifecycle state.
        tool_meta: Tool execution metadata if in TOOL_RUNNING state.
        custom_title: Optional explicit title override.
        subtitle: Optional subtitle string.

    Returns:
        Feishu Card header dictionary.
    """
    template = "blue"
    title_text = "🧠 正在深度思考..."

    if state == DashboardState.THINKING:
        template = "blue"
        title_text = custom_title or "🧠 正在深度思考..."
    elif state == DashboardState.TOOL_RUNNING:
        if tool_meta is not None:
            _, resolved_title, resolved_template = resolve_tool_header(tool_meta.tool_name, tool_meta.args_summary)
            title_text = custom_title or resolved_title
            template = resolved_template
            if not subtitle:
                subtitle = f"已耗时 {tool_meta.elapsed_seconds:.1f}s"
        else:
            title_text = custom_title or "⚙️ 正在执行工具..."
            template = "watchet"
    elif state == DashboardState.STREAMING:
        template = "blue"
        title_text = custom_title or "✍️ 正在生成回复..."
    elif state == DashboardState.COMPLETED:
        template = "green"
        title_text = custom_title or "✅ 执行完成"
    elif state == DashboardState.FAILED:
        template = "red"
        title_text = custom_title or "❌ 执行异常"

    header_dict: dict[str, object] = {
        "title": {"tag": "plain_text", "content": title_text},
        "template": template,
    }
    if subtitle:
        header_dict["subtitle"] = {"tag": "plain_text", "content": subtitle}

    return header_dict


def build_dynamic_dashboard_card(
    state: DashboardState,
    content: str,
    *,
    card_id: str = "",
    tool_meta: ToolActionMeta | None = None,
    tool_history: list[ToolActionMeta] | None = None,
    custom_title: str = "",
    subtitle: str = "",
    cost_metadata: dict[str, object] | None = None,
    task_id: str = "",
    action_elements: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Build a complete dynamic dashboard card matching Feishu CardKit specifications.

    Args:
        state: Current lifecycle state.
        content: Main Markdown text content.
        card_id: Optional CardKit streaming card identifier.
        tool_meta: Active tool metadata.
        tool_history: Completed tool history for timeline rendering.
        custom_title: Title override.
        subtitle: Subtitle override.
        cost_metadata: Token/cost metadata dictionary.
        task_id: Optional task identifier for deep-linking.
        action_elements: Interactive buttons/menus or fallback actions.

    Returns:
        Structured JSON dictionary ready for Feishu OpenAPI message dispatch.
    """
    elements: list[dict[str, object]] = []

    # 1. Tool history timeline collapsible / compact display
    if tool_history and len(tool_history) > 0:
        history_lines: list[str] = []
        for meta in tool_history[-5:]:  # show up to last 5 tools
            icon, _, _ = resolve_tool_header(meta.tool_name)
            status_symbol = "✓" if meta.status == "success" else "✗"
            history_lines.append(f"{icon} **{meta.tool_name}** `[{status_symbol} {meta.elapsed_seconds:.1f}s]`")
        if history_lines:
            elements.append(
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "\n".join(history_lines),
                    },
                }
            )
            elements.append({"tag": "hr"})

    # 2. Main content block
    if content:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": content}})
    elif state in (DashboardState.THINKING, DashboardState.TOOL_RUNNING) and not card_id:
        elements.append(
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": "正在处理任务，请稍候..."},
            }
        )

    # 3. CardKit streaming content marker
    if card_id and state not in (DashboardState.COMPLETED, DashboardState.FAILED):
        elements.append({"tag": "streaming_content"})

    # 4. Interactive or fallback action buttons
    if action_elements:
        elements.extend(action_elements)

    # 5. Footer note with cost, tokens, and task tracking
    note_parts: list[str] = []
    if cost_metadata:
        from .cards import _format_cost_note

        cost_line = _format_cost_note(cost_metadata)
        if cost_line:
            note_parts.append(cost_line)

    if task_id:
        note_parts.append(f"Task: `{task_id[:8]}`")

    if note_parts:
        elements.append(
            {
                "tag": "note",
                "elements": [{"tag": "plain_text", "content": " · ".join(note_parts)}],
            }
        )

    card: dict[str, object] = {
        "config": _CARD_CONFIG,
        "header": build_dashboard_header(
            state,
            tool_meta=tool_meta,
            custom_title=custom_title,
            subtitle=subtitle,
        ),
        "elements": elements,
    }
    if card_id:
        card["card_id"] = card_id

    return card


class DashboardStreamThrottler:
    """300ms adaptive throttler for CardKit streaming and header updates.

    Prevents triggering Feishu API rate limits (HTTP 429) while preserving
    smooth streaming animations and instant state transitions.
    """

    def __init__(self, min_interval_seconds: float = 0.3) -> None:
        self.min_interval = min_interval_seconds
        self._last_emit_time: float = 0.0
        self._last_content: str = ""
        self._last_state: DashboardState | None = None

    def should_emit(
        self,
        current_content: str,
        current_state: DashboardState,
        *,
        is_final: bool = False,
        force: bool = False,
    ) -> bool:
        """Evaluate whether a streaming card update should be dispatched.

        Args:
            current_content: Current accumulated text.
            current_state: Current dashboard lifecycle state.
            is_final: Whether this is the final stream chunk.
            force: Force emit flag (e.g. tool state transition).

        Returns:
            True if caller should emit update to Feishu CardKit.
        """
        if is_final or force:
            self._last_emit_time = time.time()
            self._last_content = current_content
            self._last_state = current_state
            return True

        # Always emit on state change (e.g. Thinking -> ToolRunning)
        if current_state != self._last_state:
            self._last_emit_time = time.time()
            self._last_content = current_content
            self._last_state = current_state
            return True

        now = time.time()
        if now - self._last_emit_time < self.min_interval:
            return False

        # If content hasn't changed, suppress duplicate API calls
        if current_content == self._last_content:
            return False

        self._last_emit_time = now
        self._last_content = current_content
        return True
