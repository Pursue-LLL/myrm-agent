"""Effectful tool detection SSOT for completion-related guards.

Consumed by the Mixed Message Guard (which tool_calls must be preserved) and by
hosts that need to know whether a run issued a state-changing call, for example
to decide which runs need an adversarial-reviewer pass or whether a failed run
may be repeated. Classification order:

1. Static alias sets are authoritative (`_MUTATION_TOOLS`,
   `INTERACTION_UI_TOOLS`).
2. Everything else resolves via registry safety metadata with a fail-closed
   default: unknown tools are assumed effectful, since a side effect must
   never go unverified.

[INPUT]
- core.security.tool_registry::resolve_safety_metadata (POS: tool safety metadata incl. MCP readOnlyHint)

[OUTPUT]
- FINISH_TOOL_NAMES: the tool a model calls to hand in its answer
- INTERACTION_UI_TOOLS: tools that carry a user-visible interaction
- is_mutating_tool(): True when the tool mutates workspace or external state
- is_substantive_final_response(): whether a message content reads as a finished answer, not narration

[POS]
The guard's shared vocabulary about tools: which call is a completion attempt, which calls a stripped message
must keep, and which tools are effectful.
"""

from __future__ import annotations

from myrm_agent_harness.core.security.tool_registry import resolve_safety_metadata

# The tool a model calls to hand in its answer (mounted in Fast Search): a call to it is a completion attempt.
FINISH_TOOL_NAMES: frozenset[str] = frozenset({"request_answer_user_tool"})

_MUTATION_TOOLS: frozenset[str] = FINISH_TOOL_NAMES | frozenset(
    {
        # 写/执行/管理类（会改变工作区或外部状态）
        "write_file",
        "create_file",
        "edit_file",
        "delete_file",
        "file_write_tool",
        "file_edit_tool",
        "file_create_tool",
        "execute_command",
        "run_terminal",
        "bash_code_execute_tool",
        "send_message",
        "git_commit",
        "git_push",
        "apply_diff",
        "delegate_task_tool",
        "spawn_subagent",
        "browser_navigate_tool",
        "browser_click_tool",
        "browser_type_tool",
        "skill_manage_tool",
        "skill_market_tool",  # install/uninstall/install_from_url 写入技能库，registry 只读标注但实为变异
        "kanban_manage_tool",
        "cron_manage_tool",
    }
)

# 交互/UI 承载类：registry 标只读，但剥离会丢失用户可见功能（提问/授权/人类接管）
INTERACTION_UI_TOOLS: frozenset[str] = frozenset(
    {
        "ask_question_tool",
        "browser_ask_human_tool",
    }
)


def is_mutating_tool(tool_name: str) -> bool:
    """Return True when the tool mutates workspace or external state (effectful).

    SSOT for hosts that need to know whether a run issued a state-changing call,
    such as post-run verification or the decision to repeat a failed run. The
    static alias set is authoritative; everything else resolves via registry
    metadata (fail-closed: unknown tools assumed effectful, since a side effect
    must never go unverified).
    """
    if tool_name in _MUTATION_TOOLS:
        return True
    return not resolve_safety_metadata(tool_name).is_read_only


_UNFINISHED_MARKERS: tuple[str, ...] = (
    "...",
    "接下来我会",
    "I'll now",
    "Let me",
    "I will now",
    "下面我来",
    "让我",
    "我现在",
    "Next, I'll",
)

_STRUCTURE_MARKERS: tuple[str, ...] = ("\n#", "\n-", "\n*", "\n1.", "```")


def is_substantive_final_response(content: str) -> bool:
    """Determine if content is a complete final response rather than in-progress narration.

    Returns True only when the content exhibits characteristics of a finished answer:
    sufficient length, structured formatting, and no trailing "unfinished" indicators.
    """
    if len(content) < 500:
        return False
    has_structure = any(marker in content for marker in _STRUCTURE_MARKERS)
    if not has_structure:
        return False
    trailing = content[-150:].strip()
    has_unfinished_marker = any(trailing.endswith(marker) or marker in trailing for marker in _UNFINISHED_MARKERS)
    return not has_unfinished_marker


__all__ = [
    "FINISH_TOOL_NAMES",
    "INTERACTION_UI_TOOLS",
    "is_mutating_tool",
    "is_substantive_final_response",
]
