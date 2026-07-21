"""Pure helpers for StreamContentCollector event parsing and persistence.

[INPUT]
- stdlib json (POS: tool result JSON decode)
- app.core.utils.ui_data_merge::deep_merge_ui_data (POS: A2UI binding dict deep-merge)

[OUTPUT]
- deep_merge_ui_data (re-export), is_memory_citation_tool, parse_tool_end_result
- collect_kanban_task_created, collect_cron_job_result
- string_keyed_dict, string_keyed_dicts

[POS]
Stateless parsing helpers for stream_collector. Keeps StreamContentCollector under file line budget.
"""

from __future__ import annotations

import json

from app.core.utils.ui_data_merge import deep_merge_ui_data

_MEMORY_CITATION_TOOL_NAMES = frozenset(
    {"memory_search", "memory_search_tool", "memory_recall", "memory_recall_tool"}
)  # legacy aliases retained for persisted message metadata


def is_memory_citation_tool(tool_name: object) -> bool:
    return isinstance(tool_name, str) and tool_name in _MEMORY_CITATION_TOOL_NAMES


def parse_tool_end_result(event: dict[str, object]) -> object | None:
    result = event.get("result")
    if isinstance(result, str):
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return None
    return result


def collect_kanban_task_created(
    entries: list[dict[str, object]],
    event: dict[str, object],
) -> None:
    if event.get("tool_name") != "kanban_add_task":
        return
    result_obj = parse_tool_end_result(event)
    if not isinstance(result_obj, dict) or result_obj.get("status") != "added":
        return
    task = result_obj.get("task")
    if not isinstance(task, dict):
        return
    task_id = task.get("task_id")
    board_id = task.get("board_id")
    title = task.get("title")
    if not all(isinstance(value, str) for value in (task_id, board_id, title)):
        return
    entries.append(
        {
            "task_id": task_id,
            "title": title,
            "board_id": board_id,
        }
    )


def collect_cron_job_result(event: dict[str, object]) -> dict[str, object] | None:
    if event.get("tool_name") != "cron_manage":
        return None
    result_obj = parse_tool_end_result(event)
    if not isinstance(result_obj, dict) or result_obj.get("status") != "success":
        return None
    return result_obj


def string_keyed_dict(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return {str(key): item for key, item in value.items() if isinstance(key, str)}


def string_keyed_dicts(values: list[object]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for value in values:
        normalized = string_keyed_dict(value)
        if normalized is not None:
            result.append(normalized)
    return result
