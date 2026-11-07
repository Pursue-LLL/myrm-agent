"""Widget 能力声明中间件 (Widget Capability Middleware)

在每次 LLM 调用的请求里插入 widget 能力声明，告知 AI 可以生成交互式 HTML widget。
声明不写入对话状态；内容与插入位置恒定。

设计原则：
1. 声明约 350 token（o200k_base，CI 门禁封顶 366），除 naked 模式外始终插入
2. 声明包含格式规范、CDN 白名单、设计指南
3. 插入位置：请求里前导连续 SystemMessage 之后、第一条非 system 消息之前
"""

from collections.abc import Awaitable, Callable, Sequence

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage

WIDGET_CAPABILITY_MARKER = "<widget_capability"

WIDGET_CAPABILITY_PROMPT = """<widget_capability>
You can create interactive HTML visualizations as artifacts. When the user's request involves data visualization, charts, diagrams, interactive demos, dashboards, or UI mockups, generate an HTML artifact.

## Format
Output a complete HTML document as an artifact with type "html". The HTML will be rendered in a secure sandboxed iframe with theme inheritance.

## Design rules
1. Use CSS variables for theming: `var(--widget-bg)`, `var(--widget-text)`, `var(--widget-primary)`, `var(--widget-border)`, `var(--widget-chart-1)` through `var(--widget-chart-5)`
2. Built-in utility classes available (Tailwind-like): flex, grid, gap-*, p-*, m-*, text-sm/base/lg, rounded, border, etc.
3. Form elements (input, select, button) are pre-styled — write bare tags
4. Background should be transparent — host provides bg via `var(--widget-bg)`
5. CDN allowlist: cdnjs.cloudflare.com, cdn.jsdelivr.net, unpkg.com, esm.sh
6. CDN scripts: use `onload="initFn()"` + `if(window.Lib) initFn();` fallback
7. SVG: `<svg width="100%" viewBox="0 0 680 H">`, use `min-height` for outermost container
8. Charts: Chart.js via CDN, use hex colors from chart variables, `responsive:true, maintainAspectRatio:false`
9. Interactive controls MUST update visuals (e.g. `chart.update()` after data changes)
10. Max ~3000 chars per widget. Keep it focused.
</widget_capability>"""


def _has_widget_capability_injected(messages: Sequence[object]) -> bool:
    """Check if widget capability has already been injected."""
    for msg in messages[:6]:
        if isinstance(msg, SystemMessage):
            content = msg.content
            if isinstance(content, str) and WIDGET_CAPABILITY_MARKER in content:
                return True
    return False


def _find_insert_idx(messages: Sequence[object]) -> int:
    """Find insertion point: after the last consecutive SystemMessage in the prefix block.

    Scans from the start; stops at the first non-SystemMessage.
    If no SystemMessage exists, returns 0 (prepend).
    """
    idx = 0
    for msg in messages:
        if isinstance(msg, SystemMessage):
            idx += 1
        else:
            break
    return idx


class WidgetCapabilityMiddleware(AgentMiddleware):  # type: ignore[type-arg]
    """Insert the widget capability declaration into every LLM request.

    Adds a SystemMessage with widget generation guidelines so the AI
    knows it can create interactive HTML artifacts.
    """

    name = "widget_capability_middleware"

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        # naked 模式下跳过 widget 能力声明
        if request.runtime is not None:
            ctx = getattr(request.runtime, "context", None)
            if isinstance(ctx, dict) and ctx.get("prompt_mode") == "naked":
                return await handler(request)

        if _has_widget_capability_injected(request.messages):
            return await handler(request)

        messages = list(request.messages)
        messages.insert(_find_insert_idx(messages), SystemMessage(content=WIDGET_CAPABILITY_PROMPT))
        return await handler(request.override(messages=messages))


widget_capability_middleware = WidgetCapabilityMiddleware()
