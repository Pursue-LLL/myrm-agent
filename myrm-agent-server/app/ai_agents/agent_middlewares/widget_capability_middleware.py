"""Widget 能力声明中间件 (Widget Capability Middleware)

在首次 LLM 调用时注入 widget 能力声明，告知 AI 可以生成交互式 HTML widget。
声明只注入一次，持久化到对话历史中。

设计原则：
1. 最小声明（~150 token）始终注入，不浪费 token
2. 声明包含格式规范、CDN 白名单、设计指南
3. 注入位置在 user_instructions 之后
"""

import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage

logger = logging.getLogger(__name__)

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
    """Inject widget capability declaration on first LLM call.

    Adds a SystemMessage with widget generation guidelines so the AI
    knows it can create interactive HTML artifacts.
    """
    name = "widget_capability_middleware"

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse | Any:
        raise NotImplementedError("WidgetCapabilityMiddleware does not support synchronous wrap_model_call")

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

        state = request.state
        raw_state_messages = state.get("messages", [])
        state_messages: list[object] = list(raw_state_messages) if isinstance(raw_state_messages, list) else []

        already_injected = _has_widget_capability_injected(state_messages) or _has_widget_capability_injected(request.messages)

        if not already_injected:
            capability_msg = SystemMessage(content=WIDGET_CAPABILITY_PROMPT)

            new_messages = list(request.messages)
            insert_idx = _find_insert_idx(new_messages)
            new_messages.insert(insert_idx, capability_msg)

            state_insert_idx = _find_insert_idx(state_messages)
            state_messages.insert(state_insert_idx, capability_msg)

            request = request.override(messages=new_messages)
            logger.info("Widget capability declaration injected at position %d", insert_idx)
        else:
            logger.debug("Widget capability already present, skipping injection")

        return await handler(request)


widget_capability_middleware = WidgetCapabilityMiddleware()
