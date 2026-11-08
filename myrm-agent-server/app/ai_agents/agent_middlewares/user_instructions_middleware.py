"""用户指令注入中间件 (User Instructions Middleware)

把 user_instructions 作为 SystemMessage 注入每次模型调用的请求，可被 GeneralAgent 各模式（full/lean/naked/search）共用。

1. agent/context_management/PROMPT_CACHE_PRACTICE.md §2 前缀稳定性保障

## 语义

1. **取值**：指令取自本次调用的 runtime context；块只插入请求副本，不写回线程状态。
   下一条消息传入的值立即生效，缺省则下一条消息没有该块。
2. **续跑**：审批、计划确认等中断恢复的请求不带指令，其 context 为空。每次新调用开始时（`before_agent`）把本次指令
   记入图状态 `instructions_snapshot`（缺省则清空）；恢复不会重新进入入口节点，续跑段因此沿用被打断那一段的快照。
3. **去重**：前 5 条消息的 System 消息里已含 `<user_instructions` 标记则视为已注入，跳过。
4. **Prompt Cache**：System Prompt 保持纯净；块紧随其后，System Prompt 作为最稳定的前缀可被跨用户共享。

## 数据流

```
客户端 user_instructions（全局指令 + 伙伴介绍）+ 服务端追加的智能体人设
    ↓
Agent context["user_instructions"]
    ↓
before_agent 写入快照 → 模型调用：context 有值用 context，否则用快照 → 插入 System Prompt 之后
```

## 消息注入位置

```
[0] SystemMessage: system prompt          ← 固定，跨用户缓存
[1] SystemMessage: <user_instructions>    ← 本中间件注入（per-user, stable）
[2] SystemMessage: <workspace_context>    ← workspace_rules_middleware（per-thread, stable, 可无）
[3] SystemMessage: <user_memory_context>  ← memory_context_middleware（每次模型调用重建，只在请求里，不写回线程状态）
[4] HumanMessage: 用户消息               ← 每轮变化
```
"""

from collections.abc import Awaitable, Callable, Sequence
from typing import Annotated, NotRequired, cast

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.types import AgentState, OmitFromSchema
from langchain_core.messages import SystemMessage
from langgraph.runtime import Runtime

# 用于检测 user_instructions 是否已注入的标记
USER_INSTRUCTIONS_MARKER = "<user_instructions"

# 图会保存并随检查点持久化、但不放进图的输入与输出的状态键。
_PRIVATE_STATE = OmitFromSchema(input=True, output=True)


class InstructionsState(AgentState[object]):
    """图状态里额外记下本轮指令，让不带 context 的续跑调用沿用；私有键，不属于图的输入与输出。"""

    instructions_snapshot: NotRequired[Annotated[str, _PRIVATE_STATE]]


def _context_instructions(runtime: Runtime | None) -> str | None:
    """本次调用 context 里的 user_instructions；context 缺失或类型不符时为 None。"""
    context = getattr(runtime, "context", None)
    raw = context.get("user_instructions") if isinstance(context, dict) else None
    return raw if isinstance(raw, str) else None


def _has_user_instructions_injected(messages: Sequence[object]) -> bool:
    """检测 user_instructions 是否已注入到消息历史中

    通过检测标记 <user_instructions 来判断。
    检查前 5 条 SystemMessage（覆盖 system prompt + user_instructions + memory_context）。

    Args:
        messages: 消息列表

    Returns:
        bool: 是否已注入
    """
    for msg in messages[:5]:
        if isinstance(msg, SystemMessage):
            content = msg.content
            if isinstance(content, str) and USER_INSTRUCTIONS_MARKER in content:
                return True
    return False


def _find_system_insert_idx(messages: Sequence[object]) -> int:
    """找到 user_instructions 应插入的位置：第一个 SystemMessage 之后。

    保证 System Prompt 作为最稳定的前缀排在最前面，
    user_instructions 紧随其后，最大化跨用户 KV Cache 命中。
    """
    for i, msg in enumerate(messages):
        if isinstance(msg, SystemMessage):
            return i + 1
    return 0


class UserInstructionsMiddleware(AgentMiddleware[InstructionsState, None, object]):
    """用户指令注入中间件

    把 user_instructions（从 context 获取，续跑时取图状态里的快照）注入每次模型调用的请求。

    设计优势：
    - System Prompt 保持纯净 → 跨用户 KV 缓存持续有效
    - 块只存在于请求里 → 下一条消息的指令立即生效，不在历史里残留
    - 续跑沿用被打断那一段的指令 → 同一轮的前缀稳定
    """

    name = "user_instructions_middleware"
    state_schema = InstructionsState

    def before_agent(self, state: InstructionsState, runtime: Runtime) -> dict[str, str]:
        # 新调用的入口节点：快照以本次指令为准，缺省即清空，下一条消息不会沿用上一条的指令。
        return {"instructions_snapshot": _context_instructions(runtime) or ""}

    async def abefore_agent(self, state: InstructionsState, runtime: Runtime) -> dict[str, str]:
        return self.before_agent(state, runtime)

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
        user_instructions = _context_instructions(request.runtime) or cast(InstructionsState, request.state).get(
            "instructions_snapshot"
        )

        # 线程状态或本次请求的前 5 条 System 消息里已有带标记的块，就不再重复插入。
        already_injected = _has_user_instructions_injected(request.state.get("messages", [])) or _has_user_instructions_injected(
            request.messages
        )

        if user_instructions and not already_injected:
            content = f"""<user_instructions priority="highest" override="true">
[ABSOLUTE OBEDIENCE OVERRIDE]
The following are project-specific constraints and instructions provided by the user. 
CRITICAL: You MUST strictly obey these instructions. In case of any conflict between these instructions and your default formatting, stylistic, or behavioral rules (e.g., <response_rules>), these user instructions SHALL take absolute precedence, provided they do not violate core security or safety rules.
---
{user_instructions}
</user_instructions>"""  # noqa: E501
            instructions_msg = SystemMessage(content=content)

            new_messages = list(request.messages)
            new_messages.insert(_find_system_insert_idx(new_messages), instructions_msg)
            request = request.override(messages=new_messages)

        return await handler(request)


user_instructions_middleware = UserInstructionsMiddleware()
