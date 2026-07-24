"""Pure helpers for StreamContentCollector event parsing and persistence.

[INPUT]
- stdlib json (POS: tool result JSON decode)

[OUTPUT]
- deep_merge_ui_data, is_memory_citation_tool, parse_tool_end_result
- collect_kanban_task_created, collect_cron_job_result
- collect_clarification_required, collect_plan_confirmation_status
- string_keyed_dict, string_keyed_dicts

[POS]
Stateless parsing helpers for stream_collector. Keeps StreamContentCollector under file line budget.
"""

from __future__ import annotations

import json


def deep_merge_ui_data(
    base: dict[str, object],
    updates: dict[str, object],
) -> dict[str, object]:
    """Deep-merge A2UI binding dicts; nested dicts merge, leaves in updates win."""
    merged: dict[str, object] = dict(base)
    for key, value in updates.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = deep_merge_ui_data(existing, value)
        else:
            merged[key] = value
    return merged

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


def collect_clarification_required(
    event: dict[str, object],
) -> dict[str, object] | None:
    """Build durable extra_data.clarification from clarification_required SSE."""
    data = event.get("data")
    if not isinstance(data, dict):
        return None

    payload = string_keyed_dict(data)
    if payload is None:
        return None

    clarification: dict[str, object] = {"answered": False}

    source = payload.get("source")
    if isinstance(source, str) and source.strip():
        clarification["source"] = source.strip()
        clarification["isResumeMode"] = source.strip() != "deep_research"
    else:
        clarification["isResumeMode"] = True

    title = payload.get("title")
    if isinstance(title, str) and title.strip():
        clarification["title"] = title.strip()

    form = payload.get("form")
    if isinstance(form, dict):
        normalized_form = string_keyed_dict(form)
        if normalized_form is not None:
            clarification["form"] = normalized_form

    options = payload.get("options")
    if isinstance(options, list):
        option_labels = [str(item) for item in options if isinstance(item, str) and item.strip()]
        if option_labels:
            clarification["options"] = option_labels

    allow_multiple = payload.get("allow_multiple")
    if allow_multiple is None:
        allow_multiple = payload.get("allowMultiple")
    if isinstance(allow_multiple, bool):
        clarification["allowMultiple"] = allow_multiple

    question = payload.get("question") or payload.get("prompt")
    if isinstance(question, str) and question.strip():
        clarification["question"] = question.strip()

    if len(clarification) <= 2 and "form" not in clarification:
        return None
    return clarification


def collect_plan_confirmation_status(
    data: dict[str, object],
) -> dict[str, object] | None:
    """Build durable extra_data.planConfirmation from deep-research status events."""
    phase = data.get("phase")
    status = data.get("status")
    if phase != "plan_confirm" or not isinstance(status, str):
        return None

    if status == "waiting":
        raw_plan_items = data.get("plan_items")
        plan_items = string_keyed_dicts(raw_plan_items if isinstance(raw_plan_items, list) else [])
        plan_text = data.get("plan")
        if isinstance(plan_text, str) and plan_text.strip():
            plan = plan_text.strip()
        elif plan_items:
            plan = "\n".join(
                f"{index + 1}. {str(item.get('content', '')).strip()}"
                for index, item in enumerate(plan_items)
                if str(item.get("content", "")).strip()
            )
        else:
            plan = ""

        result: dict[str, object] = {
            "plan": plan,
            "status": "waiting",
            "source": "deep_research",
        }
        if plan_items:
            result["planItems"] = plan_items
        total_items = data.get("total_items")
        if isinstance(total_items, int):
            result["totalItems"] = total_items
        goal = data.get("goal")
        if isinstance(goal, str) and goal.strip():
            result["goal"] = goal.strip()
        return result

    if status == "resolved":
        modified = data.get("modified")
        return {
            "status": "edited" if modified else "confirmed",
        }

    return None
