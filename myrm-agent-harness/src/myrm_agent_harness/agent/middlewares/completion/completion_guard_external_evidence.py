"""External evidence gate helpers for CompletionGuard.

Detects freshness-sensitive user requests and verifies that the session
CallRecord window contains successful web/browser/MCP evidence before
allowing completion. MCP evidence covers both PTC bash imports
(``skills.mcp_*``) and Direct FC tool calls (``mcp__{server}__{tool}``).
Intercepted calls (``success_level is None``) never count as evidence —
an unexecuted tool provides no external data.

Whether a request needs external data at all is decided by
``completion_guard_freshness``; this module checks the run's records against it.

[INPUT]
- langchain_core.messages::HumanMessage (POS: human turn content extraction)
- completion.completion_guard_freshness::demands_external_evidence (POS: does the request need fresh external data)
- agent.security.guards.loop_guard::CallRecord (POS: loop guard types)
- toolkits.mcp.config::is_mcp_tool_name (POS: Direct FC MCP tool-name recognition)

[OUTPUT]
- build_external_evidence_reason(): block reason when evidence is required but missing
- has_external_evidence(): True when web/browser or MCP evidence exists
- can_produce_external_evidence(): True when a set of mounted tools could ever produce such evidence
- extract_latest_human_text(): latest non-empty human message text

[POS]
CompletionGuard external-evidence policy module. Mirrors deliverable_write_verifier
separation — keeps completion_guard.py focused on orchestration and mixed-message guard.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from langchain_core.messages import HumanMessage

from myrm_agent_harness.agent.middlewares.completion.completion_guard_freshness import demands_external_evidence
from myrm_agent_harness.toolkits.mcp.config import is_mcp_tool_name

_BASH_TOOL_NAME = "bash_code_execute_tool"
_MCP_PTC_BASH_MARKER = "skills.mcp_"

_EXTERNAL_EVIDENCE_TOOLS: frozenset[str] = frozenset(
    {
        "web_search_tool",
        "web_fetch_tool",
        "browser_navigate_tool",
        "browser_extract_tool",
        "browser_snapshot_tool",
        "browser_inspect_tool",
    }
)


def extract_latest_human_text(messages: list[object]) -> str | None:
    from myrm_agent_harness.agent.skills.runtime.skill_catalog_delivery import (
        strip_catalog_blocks,
    )

    for message in reversed(messages):
        if not isinstance(message, HumanMessage):
            continue
        if isinstance(message.content, str):
            text = strip_catalog_blocks(message.content).strip()
            if text:
                return text
            continue
        if isinstance(message.content, list):
            parts: list[str] = []
            for item in message.content:
                if isinstance(item, dict):
                    block_text = item.get("text")
                    if isinstance(block_text, str) and block_text.strip():
                        cleaned = strip_catalog_blocks(block_text).strip()
                        if cleaned:
                            parts.append(cleaned)
            if parts:
                return " ".join(parts)
    return None


def _bash_command_text(args: object) -> str:
    if not isinstance(args, dict):
        return ""
    command = args.get("command")
    if isinstance(command, str):
        return command
    return ""


def _bash_mcp_ptc_evidence_succeeded(record: object) -> bool:
    """True when bash executed a successful MCP PTC import path (skills.mcp_*).

    Intercepted calls (``success_level is None``) never count as evidence —
    an unexecuted tool provides no external data.
    """
    tool_name = getattr(record, "tool_name", "")
    if tool_name != _BASH_TOOL_NAME:
        return False
    success_level = getattr(record, "success_level", None)
    if success_level is None:
        return False
    if getattr(success_level, "name", "") == "FAILURE":
        return False
    args = getattr(record, "args", None)
    return _MCP_PTC_BASH_MARKER in _bash_command_text(args)


def _mcp_direct_evidence_succeeded(record: object) -> bool:
    """True when a Direct FC MCP tool call succeeded (mcp__{server}__{tool}).

    Small MCP servers (schema <= Direct FC threshold) are bound as first-class
    tools rather than routed through bash PTC, so their tool name — not a
    ``skills.mcp_*`` bash import — is the external evidence marker.

    Intercepted calls (``success_level is None``) never count as evidence —
    an unexecuted tool provides no external data.
    """
    tool_name = getattr(record, "tool_name", "")
    if not is_mcp_tool_name(tool_name):
        return False
    success_level = getattr(record, "success_level", None)
    if success_level is None:
        return False
    return getattr(success_level, "name", "") != "FAILURE"


def has_external_evidence(records: Sequence[object]) -> bool:
    for record in records:
        if _bash_mcp_ptc_evidence_succeeded(record):
            return True
        if _mcp_direct_evidence_succeeded(record):
            return True
        tool_name = getattr(record, "tool_name", "")
        if tool_name not in _EXTERNAL_EVIDENCE_TOOLS:
            continue
        success_level = getattr(record, "success_level", None)
        if success_level is None:
            continue
        if getattr(success_level, "name", "") == "FAILURE":
            continue
        return True
    return False


def can_produce_external_evidence(tool_names: Iterable[str]) -> bool:
    """True when a run holding ``tool_names`` could ever make ``has_external_evidence`` true.

    A shell counts: it may import an MCP server through ``skills.mcp_*``, which is evidence.
    """
    return any(
        name in _EXTERNAL_EVIDENCE_TOOLS or name == _BASH_TOOL_NAME or is_mcp_tool_name(name) for name in tool_names
    )


def build_external_evidence_reason(
    *,
    messages: list[object],
    records: Sequence[object],
) -> str | None:
    latest_human = extract_latest_human_text(messages)
    if not latest_human or not demands_external_evidence(latest_human):
        return None
    if has_external_evidence(records):
        return None
    excerpt = latest_human.replace("\n", " ").strip()
    if len(excerpt) > 200:
        excerpt = f"{excerpt[:200]}..."
    return f"latest user request hints external/freshness need: '{excerpt}'"


__all__ = [
    "build_external_evidence_reason",
    "can_produce_external_evidence",
    "extract_latest_human_text",
    "has_external_evidence",
]
