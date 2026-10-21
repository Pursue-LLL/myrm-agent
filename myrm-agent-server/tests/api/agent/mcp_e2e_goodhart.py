"""Goodhart guard helpers for 12306 MCP Agent E2E tests."""

from __future__ import annotations

import re

_ITERATION_LIMIT_MARKERS = (
    "iteration limit",
    "iterations limit",
    "max iteration",
    "迭代次数",
    "达到最大迭代",
    "iteration_limit",
)

_GET_TICKETS_TOKENS = ("get_tickets", "get-tickets")


def mcp_skill_was_invoked(collected_data: list[dict[str, object]], marker: str) -> bool:
    """True when the configured MCP skill was genuinely engaged via PTC fingerprints."""
    marker = marker.lower()
    for event in collected_data:
        if event.get("type") != "tasks_steps":
            continue
        tool_name = event.get("tool_name")
        items = event.get("data")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            if tool_name == "skill_select_tool" and marker in str(item.get("skill_name", "")).lower():
                return True
            if tool_name == "bash_code_execute_tool" and marker in str(item.get("code", "")).lower():
                return True
            if tool_name == "file_read_tool" and marker in str(item.get("file_path", "")).lower():
                return True
    return False


def mcp_ptc_bash_was_engaged(collected_data: list[dict[str, object]], marker: str) -> bool:
    """True when bash executed PTC import path (success preferred, attempt required)."""
    marker = marker.lower()
    saw_attempt = False
    for event in collected_data:
        if event.get("type") != "tasks_steps":
            continue
        if event.get("tool_name") != "bash_code_execute_tool":
            continue
        items = event.get("data")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code", ""))
            if "skills.mcp_" not in code or marker not in code:
                continue
            if event.get("status") == "success":
                return True
            saw_attempt = True
    return saw_attempt


def _code_mentions_get_tickets(code: str) -> bool:
    normalized = code.lower().replace("-", "_")
    return "get_tickets" in normalized


def _path_mentions_get_tickets(path: str) -> bool:
    lowered = path.lower()
    return any(token in lowered for token in _GET_TICKETS_TOKENS)


def mcp_ptc_get_tickets_engaged(collected_data: list[dict[str, object]], marker: str) -> bool:
    """True when PTC chain reached get_tickets docs or bash import (not date/station-only)."""
    marker = marker.lower()
    for event in collected_data:
        if event.get("type") != "tasks_steps":
            continue
        tool_name = event.get("tool_name")
        items = event.get("data")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            if tool_name == "file_read_tool":
                path = str(item.get("file_path", ""))
                if marker in path.lower() and _path_mentions_get_tickets(path):
                    return True
            if tool_name == "bash_code_execute_tool":
                code = str(item.get("code", ""))
                if marker in code.lower() and _code_mentions_get_tickets(code):
                    return True
    return False


def mcp_bash_get_tickets_succeeded(collected_data: list[dict[str, object]], marker: str) -> bool:
    """True when bash successfully executed code that imports/calls get_tickets for the MCP skill."""
    marker = marker.lower()
    for event in collected_data:
        if event.get("type") != "tasks_steps":
            continue
        if event.get("tool_name") != "bash_code_execute_tool":
            continue
        if event.get("status") != "success":
            continue
        items = event.get("data")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code", ""))
            if marker in code.lower() and _code_mentions_get_tickets(code):
                return True
        stdout = event.get("stdout")
        if isinstance(stdout, str) and answer_looks_like_ticket_result(stdout):
            return True
    return False


def _strip_iteration_limit_suffix(text: str) -> str:
    lowered = text.lower()
    cut_at = len(text)
    for marker in _ITERATION_LIMIT_MARKERS:
        idx = lowered.find(marker)
        if idx != -1:
            cut_at = min(cut_at, idx)
    return text[:cut_at]


def mcp_get_tickets_delivered(collected_data: list[dict[str, object]], marker: str) -> bool:
    """True when MCP get-tickets returned train-list payload in tasks_steps metadata."""
    marker = marker.lower()
    for event in collected_data:
        if event.get("type") != "tasks_steps":
            continue
        items = event.get("data")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict) or item.get("type") != "mcp":
                continue
            if marker not in str(item.get("skill_name", "")).lower():
                continue
            calls = item.get("calls")
            if not isinstance(calls, list):
                continue
            for call in calls:
                if not isinstance(call, dict):
                    continue
                if "get-tickets" not in str(call.get("tool_name", "")).lower():
                    continue
                preview = str(call.get("result_preview", ""))
                preview_lower = preview.lower()
                if "missing required argument" in preview_lower:
                    continue
                if preview_lower.startswith("{'error'") or '"error":' in preview_lower[:120]:
                    continue
                if re.search(r"[GDC]\d{1,4}", preview) or "车次" in preview:
                    return True
    return False


def answer_looks_like_ticket_result(full_answer: str) -> bool:
    """Heuristic guard: final answer should look like a ticket listing, not iteration-limit boilerplate."""
    text = _strip_iteration_limit_suffix(full_answer).strip()
    if len(text) < 20:
        return False
    lowered = text.lower()
    if any(marker in lowered for marker in _ITERATION_LIMIT_MARKERS):
        return False
    if re.search(r"[GDC]\d{1,4}", text):
        return True
    if "高铁" in text and "车次" in text:
        return True
    if "车次" in text and ("出发" in text or "到达" in text or "历时" in text):
        return True
    if re.search(r"\d{1,2}:\d{2}", text) and "北京" in text and "上海" in text:
        return True
    return False


def assert_12306_ticket_evidence_delivered(
    collected_data: list[dict[str, object]],
    full_answer: str,
    *,
    marker: str = "12306",
) -> None:
    """Primary PASS anchor: MCP metadata deliver; secondary fallback bash stdout + answer."""
    if mcp_get_tickets_delivered(collected_data, marker):
        return
    bash_ok = mcp_bash_get_tickets_succeeded(collected_data, marker)
    answer_ok = answer_looks_like_ticket_result(full_answer)
    assert bash_ok and answer_ok, (
        "12306 ticket query did not deliver MCP get-tickets metadata and lacks corroborating "
        "bash stdout + final answer evidence (Goodhart guard)"
    )
