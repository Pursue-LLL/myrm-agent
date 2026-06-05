"""用户指令注入中间件 (User Instructions Middleware)

在首次 LLM 调用时注入 user_instructions，并持久化到对话历史中。
可被 GeneralAgent 各模式（full/lean/naked/search）共用。

1. agent/context_management/PROMPT_CACHE_PRACTICE.md §2 前缀稳定性保障

## 设计原则

1. **唯一性保证**：user_instructions 只注入一次
   - 通过 `<user_instructions>` 标记检测避免重复
   - 同时检测 state["messages"] 和 request.messages

2. **持久化**：注入到 state["messages"]，持久化到对话历史

3. **Prompt Cache 优化**：
   - System Prompt 保持纯净，最大化跨用户 KV 缓存命中率
   - user_instructions 注入到 System Prompt **之后**，保证 System Prompt
     作为最稳定的前缀可被跨用户共享

## 重复注入问题及解决方案

### 问题场景
多轮对话时，前端发送的 chat_history 可能已包含之前注入的 user_instructions。
如果只检测 state["messages"]（新 Agent 运行时为空），会导致重复注入。

### 解决方案
同时检测两个消息来源：
- `state["messages"]`: 当前 Agent 运行状态中的消息
- `request.messages`: 包含 chat_history 转换后的完整消息列表

只要任一来源包含 `<user_instructions>` 标记，即跳过注入。

## 数据流

```
前端 user_instructions (全局指令 + 智能体指令)
    ↓
后端 API (user_instructions 字段)
    ↓
Agent context["user_instructions"]
    ↓
中间件检测 → 首次注入（System Prompt 之后） → 持久化到 state["messages"]
    ↓
后续轮次：检测到标记 → 跳过注入
```

## 消息注入位置

```
[0] SystemMessage: system prompt          ← 固定，跨用户缓存
[1] SystemMessage: <user_instructions>    ← 本中间件注入（per-user, stable）
[2] SystemMessage: <workspace_context>    ← workspace_rules_middleware（per-workspace, stable, 可无）
[3] SystemMessage: Stable `<user_memory_context>` ← memory_context_middleware（Stable）
[4] HumanMessage（可选）: Learned <<<UNTRUSTED_DATA>>> ← memory_context_middleware（在同用户 Stable 前缀之后）
[5] HumanMessage: 用户消息               ← 每轮变化
```
"""

from collections.abc import Awaitable, Callable, Sequence

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage

# 用于检测 user_instructions 是否已注入的标记
USER_INSTRUCTIONS_MARKER = "<user_instructions"


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


class UserInstructionsMiddleware(AgentMiddleware):  # type: ignore[type-arg]
    """用户指令注入中间件

    在首次 LLM 调用时注入 user_instructions（从 context 获取）。

    设计优势：
    - System Prompt 保持纯净 → 跨用户 KV 缓存持续有效
    - user_instructions 只注入一次 → 避免 token 浪费
    - 注入到 state["messages"] → 持久化到对话历史
    """

    name = "user_instructions_middleware"

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        raise NotImplementedError("UserInstructionsMiddleware does not support synchronous wrap_model_call")

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        state = request.state
        raw_state_messages = state.get("messages", [])
        state_messages: list[object] = list(raw_state_messages) if isinstance(raw_state_messages, list) else []

        # 从 context 获取 user_instructions
        user_instructions: str | None = None
        if request.runtime is not None:
            context = getattr(request.runtime, "context", None)
            if isinstance(context, dict):
                raw_ui = context.get("user_instructions")
                if isinstance(raw_ui, str):
                    user_instructions = raw_ui

        # 首次注入 user_instructions（检测标记避免重复）
        # 注意：同时检测 state["messages"] 和 request.messages
        # - state["messages"]: 当前 Agent 运行状态中的消息
        # - request.messages: 包含 chat_history 的完整消息列表（多轮对话可能已包含之前注入的指令）
        already_injected = _has_user_instructions_injected(state_messages) or _has_user_instructions_injected(request.messages)

        if user_instructions and not already_injected:
            content = f"""<user_instructions priority="highest" override="true">
[ABSOLUTE OBEDIENCE OVERRIDE]
The following are project-specific constraints and instructions provided by the user. 
CRITICAL: You MUST strictly obey these instructions. In case of any conflict between these instructions and your default formatting, stylistic, or behavioral rules (e.g., <response_rules>), these user instructions SHALL take absolute precedence, provided they do not violate core security or safety rules.
---
{user_instructions}
</user_instructions>"""  # noqa: E501
            instructions_msg = SystemMessage(content=content)

            # 先复制 request.messages 再修改 state_messages，
            # 因为两者可能是同一个列表对象的引用
            new_messages = list(request.messages)
            insert_idx = _find_system_insert_idx(new_messages)
            new_messages.insert(insert_idx, instructions_msg)

            state_insert_idx = _find_system_insert_idx(state_messages)
            state_messages.insert(state_insert_idx, instructions_msg)

            request = request.override(messages=new_messages)

        return await handler(request)


user_instructions_middleware = UserInstructionsMiddleware()
