"""无 LLM 时的确定性摘要：从消息中提取目标、动作、已完成操作与文件。

[INPUT]
- langchain_core.messages (POS: 消息类型)
- core.message_origin::is_user_authored_human_message (POS: Message-provenance primitives shared by the approval, security, memory-context and context-management layers.)
- utils.chat_utils::extract_text_content (POS: 多模态消息可见文本提取)
- agent.context_management.infra.schemas::StructuredSummary (POS: 结构化摘要类型)

[OUTPUT]
- _build_deterministic_summary / _extract_focus_topic: 确定性摘要与压缩意图提取

[POS]
`summarize_processor/` 的降级路径；不依赖 LLM。
"""

from __future__ import annotations

import re

from langchain_core.messages import AIMessage, BaseMessage

from myrm_agent_harness.core.message_origin import is_user_authored_human_message
from myrm_agent_harness.utils.chat_utils import extract_text_content

from ....infra.schemas import StructuredSummary

_COMPACTED_PATTERN = re.compile(r"COMPACTED: (\w+)\((.+?)\)")
_FALLBACK_GOAL_MAX_CHARS = 300
_FALLBACK_ACTION_MAX_CHARS = 120


def _build_deterministic_summary(
    messages: list[BaseMessage], metadata: dict[str, object], chat_id: str | None = None
) -> StructuredSummary:
    """Extract key information from messages without LLM.

    Extracts:
    - user_goal from the last message the user wrote
    - last_action from the last AIMessage content
    - completed_actions from COMPACTED: patterns in compressed tool results
    - files_modified from ArtifactTracker
    - context_dump_path from metadata snapshot path
    """
    user_goal = "[Unable to extract goal]"
    active_task = ""
    last_action = ""
    completed_actions: list[str] = []
    files_modified: list[str] = []

    for msg in reversed(messages):
        if is_user_authored_human_message(msg):
            content = extract_text_content(msg.content)
            goal = content[:_FALLBACK_GOAL_MAX_CHARS] + ("…" if len(content) > _FALLBACK_GOAL_MAX_CHARS else "")
            if not active_task:
                active_task = goal
            if user_goal == "[Unable to extract goal]":
                user_goal = goal

        if isinstance(msg, AIMessage) and not last_action:
            content = extract_text_content(msg.content)
            last_action = content[:_FALLBACK_ACTION_MAX_CHARS]
            if len(content) > _FALLBACK_ACTION_MAX_CHARS:
                last_action += "…"

        if user_goal != "[Unable to extract goal]" and last_action:
            break

    for msg in messages:
        for match in _COMPACTED_PATTERN.finditer(extract_text_content(msg.content)):
            tool_name, identifier = match.group(1), match.group(2)
            action = f"{tool_name}: {identifier}"
            if action not in completed_actions:
                completed_actions.append(action)

    try:
        from ....tracking.artifact_tracker import get_artifact_tracker

        if chat_id:
            tracker = get_artifact_tracker(chat_id)
            if tracker:
                all_files = set(tracker.created_files) | set(tracker.modified_files)
                files_modified = sorted(all_files)
    except Exception:
        pass

    context_dump_path = ""
    snapshot_path = metadata.get("context_snapshot_path")
    if isinstance(snapshot_path, str) and snapshot_path:
        context_dump_path = snapshot_path

    return StructuredSummary(
        user_goal=f"[Deterministic fallback — verify via files/commands] {user_goal}",
        completed_actions=completed_actions[:10],
        key_findings=[],
        errors_and_fixes=[],
        files_modified=files_modified[:20],
        last_action=last_action,
        context_dump_path=context_dump_path,
        active_task=active_task,
    )


def _extract_focus_topic(metadata: dict[str, object]) -> str:
    """Extract CompressionIntent.user_goal_hint from metadata as focus topic."""
    intent_data = metadata.get("compression_intent")
    if isinstance(intent_data, dict):
        hint = intent_data.get("user_goal_hint", "")
        if isinstance(hint, str):
            return hint.strip()
    return ""
