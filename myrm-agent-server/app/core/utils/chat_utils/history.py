"""[INPUT]
- myrm_agent_harness.utils.chat_utils / image_utils / json_parsing (POS: framework primitives)

[OUTPUT]
- convert_chat_history / parse_judge_json plus the agent-history expansion helpers.

[POS]
Chat helper module: history conversion and judge verdict parsing.
"""

from __future__ import annotations

import json
import logging
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from myrm_agent_harness.utils.chat_utils import (
    ChatHistory,
)
from myrm_agent_harness.utils.json_parsing import parse_llm_json_object

from .images import _degrade_old_images
from .multimodal import _process_human_content

logger = logging.getLogger(__name__)


def parse_judge_json(raw: str) -> dict[str, object] | None:
    """Parse a judge verdict object that requires a ``done`` key.

    Extends :func:`parse_llm_json_object` with the contract shared by the
    kanban verifier and the goal semantic judge: the returned object must
    carry a ``done`` field. When several objects are recoverable, the one
    with ``done`` is preferred and, among those, the *last* one wins —
    reasoning providers tend to put format examples first and the real
    verdict last. String forms (``"True"``/``"yes"``/``"1"``) and numeric
    forms (``1``/``0``) are normalized to Python bools.
    """
    last_verdict = parse_llm_json_object(raw, require_key="done")
    if last_verdict is None:
        return None
    done = last_verdict.get("done")
    if isinstance(done, str):
        last_verdict["done"] = done.strip().lower() in ("true", "yes", "1")
    elif isinstance(done, (int, float)):
        last_verdict["done"] = done != 0
    return last_verdict


def _try_parse_agent_history(content: str) -> dict[str, object] | None:
    """尝试解析 __agent_history JSON 标记。返回 None 表示普通文本。"""
    if not content.startswith('{"__agent_history"'):
        return None
    try:
        data = json.loads(content)
        if isinstance(data, dict) and data.get("__agent_history") is True:
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def _build_tool_result_text(tool_name: str, sources: list[dict[str, object]]) -> str:
    """从 sources 数据构建 ToolMessage 的结果文本"""
    if "search" in tool_name.lower():
        lines = []
        for s in sources:
            if s.get("type") in ("web_search", "web_fetch"):
                title = s.get("title", "Untitled")
                url = s.get("url", "")
                snippet = s.get("snippet", "")
                entry = f"[{s.get('index', '?')}] {title}\n    URL: {url}"
                if snippet:
                    entry += f"\n    {snippet}"
                lines.append(entry)
        return "\n\n".join(lines) if lines else "Search completed with results."

    if any(kw in tool_name.lower() for kw in ("fetch", "browse", "webpage")):
        urls = [str(s.get("url", "")) for s in sources if s.get("type") == "web_fetch" and s.get("url")]
        return f"Fetched content from: {', '.join(urls)}" if urls else "Web page content fetched."

    if "skill" in tool_name.lower() or "mcp" in tool_name.lower():
        skills = [str(s.get("skill_name", "")) for s in sources if s.get("type") == "mcp" and s.get("skill_name")]
        return f"MCP skills executed: {', '.join(skills)}" if skills else "Skill executed successfully."

    return f"Tool '{tool_name}' completed successfully."


def _expand_agent_history(content: str) -> list[BaseMessage]:
    """将 __agent_history JSON 还原为 LangGraph 原生消息序列。

    输出: AIMessage(tool_calls=[...]) + ToolMessage(...) × N + AIMessage(content=...)
    这样 LangGraph Agent 在后续决策时能原生识别之前的工具调用历史。
    """
    data = _try_parse_agent_history(content)
    if data is None:
        return [AIMessage(content=content)]

    messages: list[BaseMessage] = []
    tool_calls_data: list[dict[str, object]] = data.get("tool_calls", [])  # type: ignore[assignment]
    sources: list[dict[str, object]] = data.get("sources", [])  # type: ignore[assignment]
    text_content: str = data.get("content", "")  # type: ignore[assignment]

    if tool_calls_data:
        lc_tool_calls: list[dict[str, object]] = []
        tool_messages: list[ToolMessage] = []

        for tc in tool_calls_data:
            tc_name = str(tc.get("name", "unknown"))
            tc_id = f"hist_{uuid4().hex[:8]}"
            tc_args = tc.get("args", {})

            lc_tool_calls.append(
                {
                    "name": tc_name,
                    "args": tc_args if isinstance(tc_args, dict) else {},
                    "id": tc_id,
                    "type": "tool_call",
                }
            )

            result_text = _build_tool_result_text(tc_name, sources)
            tool_messages.append(
                ToolMessage(
                    content=result_text,
                    tool_call_id=tc_id,
                    name=tc_name,
                )
            )

        if lc_tool_calls:
            messages.append(AIMessage(content="", tool_calls=lc_tool_calls))
            messages.extend(tool_messages)

    if text_content:
        messages.append(AIMessage(content=text_content))
    elif not messages:
        messages.append(AIMessage(content=""))

    return messages


_MAX_IMAGE_TURNS = 2


async def convert_chat_history(
    history: object,
    max_image_turns: int = _MAX_IMAGE_TURNS,
    model_cfg: object | None = None,
    vision_fallback_model_cfg: object | None = None,
) -> ChatHistory:
    """将聊天历史转换为 LangChain 消息格式

    支持：
    - 图片内容处理（human 消息）
    - Agent 工具历史还原（assistant 消息中的 __agent_history JSON）
    - 历史图片降级：仅保留最近 max_image_turns 个 turn 的图片，
      更旧的 turn 中的图片替换为文本占位符（节省上下文窗口）

    Args:
        history: 原始格式 [["human", content], ["assistant", content], ...]
                或已转换格式 [HumanMessage, AIMessage, ...]
        max_image_turns: 保留图片的最大 turn 数（从最新往回计）
    """
    if not history:
        return []

    if isinstance(history, list) and history and isinstance(history[0], BaseMessage):
        return history

    if not isinstance(history, list):
        return []

    messages: list[BaseMessage] = []
    for item in history:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        role, content = item[0], item[1]

        if role == "custom":
            # Extension private state: does NOT participate in LLM context (0 token leak)
            continue
        elif role == "custom_message":
            meta = item[2] if len(item) > 2 and isinstance(item[2], dict) else {}
            custom_type = meta.get("custom_type") or "custom"
            display = meta.get("display", True)
            retention = meta.get("retention", "persistent")
            details = meta.get("details")
            msg = HumanMessage(
                content=str(content),
                additional_kwargs={
                    "is_custom_message": True,
                    "custom_type": custom_type,
                    "display": display,
                    "retention": retention,
                    **({"details": details} if details is not None else {}),
                },
            )
            messages.append(msg)
        elif role == "human":
            meta = item[2] if len(item) > 2 and isinstance(item[2], dict) else {}
            processed_content = await _process_human_content(content, meta, model_cfg, vision_fallback_model_cfg)
            msg = HumanMessage(content=processed_content)
            if meta.get("is_custom_message") or meta.get("custom_type"):
                msg.additional_kwargs["is_custom_message"] = True
                msg.additional_kwargs["custom_type"] = meta.get("custom_type", "custom")
                msg.additional_kwargs["display"] = meta.get("display", True)
                msg.additional_kwargs["retention"] = meta.get("retention", "persistent")
                if "details" in meta:
                    msg.additional_kwargs["details"] = meta["details"]
            messages.append(msg)
        else:
            assistant_meta = item[2] if len(item) > 2 and isinstance(item[2], dict) else {}
            text_content = str(content) if not isinstance(content, str) else content
            expanded = _expand_agent_history(text_content)
            reasoning_content = assistant_meta.get("reasoning_content")
            if isinstance(reasoning_content, str) and reasoning_content and expanded:
                for msg in expanded:
                    if isinstance(msg, AIMessage):
                        msg.additional_kwargs["reasoning_content"] = reasoning_content
                        break
            messages.extend(expanded)

    _degrade_old_images(messages, max_image_turns)

    return messages
