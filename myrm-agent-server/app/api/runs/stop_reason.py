"""Stop-reason normalization for Unified Runs Hub.

[INPUT]
- app.api.runs.schemas::RunStatus (POS: unified run status enum)
- Cron/Kanban/Shell metadata and error strings

[OUTPUT]
- normalize_stop_reason / extract_stop_reason_from_metadata helpers
- stop_reason_from_error / stop_reason_from_shell_task inference

[POS]
Pure normalization layer shared by GET /runs aggregation fetchers.
"""

from __future__ import annotations

from app.api.runs.schemas import RunStatus

_STOP_REASON_CATEGORIES = frozenset({"limit", "cancelled", "error", "other"})


def normalize_stop_reason(raw: object) -> dict[str, object] | None:
    if not isinstance(raw, dict):
        return None
    code_obj = raw.get("code")
    if not isinstance(code_obj, str) or not code_obj.strip():
        return None
    code = code_obj.strip()
    category_obj = raw.get("category")
    category = category_obj if isinstance(category_obj, str) and category_obj in _STOP_REASON_CATEGORIES else "other"
    message_obj = raw.get("message")
    message = message_obj.strip() if isinstance(message_obj, str) and message_obj.strip() else code.replace("_", " ")
    normalized: dict[str, object] = {
        "code": code,
        "category": category,
        "message": message,
    }
    detail_obj = raw.get("detail")
    if isinstance(detail_obj, dict):
        normalized["detail"] = {str(k): v for k, v in detail_obj.items() if isinstance(k, str)}
    return normalized


def _extract_step_item_text(items: object) -> str | None:
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
    return None


def extract_stop_reason_from_metadata(metadata: dict[str, object] | None) -> dict[str, object] | None:
    if metadata is None:
        return None
    direct = normalize_stop_reason(metadata.get("stopReason"))
    if direct is not None:
        return direct
    steps_obj = metadata.get("progressSteps")
    if not isinstance(steps_obj, list):
        return None
    for step_obj in reversed(steps_obj):
        if not isinstance(step_obj, dict):
            continue
        step_key = step_obj.get("step_key")
        if step_key == "iteration_limit_reached":
            message = "Iteration limit reached"
            step_text = _extract_step_item_text(step_obj.get("items"))
            if step_text:
                message = f"Iteration limit reached ({step_text})"
            return {
                "code": "iteration_limit_reached",
                "category": "limit",
                "message": message,
            }
    return None


def stop_reason_from_error(error: str | None, status: RunStatus) -> dict[str, object] | None:
    if status == "timed_out":
        return {
            "code": "timed_out",
            "category": "limit",
            "message": error.strip() if isinstance(error, str) and error.strip() else "Execution timed out",
        }
    if status == "cancelled":
        return {
            "code": "user_cancelled",
            "category": "cancelled",
            "message": error.strip() if isinstance(error, str) and error.strip() else "Run cancelled",
        }
    if not error:
        return None
    error_text = error.strip()
    if not error_text:
        return None
    if "tool call limit exceeded" in error_text.lower() or "max_replan_attempts exceeded" in error_text.lower():
        return {
            "code": "engine_limit_reached",
            "category": "limit",
            "message": error_text,
        }
    return {
        "code": "error",
        "category": "error",
        "message": error_text,
    }


def stop_reason_from_shell_task(task: object, status: RunStatus) -> dict[str, object] | None:
    if status in {"running", "ok"}:
        return None
    error_category_obj = getattr(task, "error_category", None)
    error_category = error_category_obj if isinstance(error_category_obj, str) and error_category_obj else None
    preview_obj = getattr(task, "result_preview", None)
    preview = preview_obj.strip() if isinstance(preview_obj, str) and preview_obj.strip() else None
    payload: dict[str, object]
    if status == "cancelled":
        payload = {
            "code": "user_cancelled",
            "category": "cancelled",
            "message": preview or "Shell task cancelled",
        }
    else:
        payload = {
            "code": "error",
            "category": "error",
            "message": preview or "Shell task failed",
        }
    if error_category is not None:
        payload["detail"] = {"error_category": error_category}
    return payload
