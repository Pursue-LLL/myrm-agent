"""Evicted tool output references: matching a stored stdout/stderr file to the progress step it belongs to.

[INPUT]
- (none; stateless transforms over progress step dicts)

[OUTPUT]
- BASH_EXECUTE_TOOL: tool name that the unmatched evicted output falls back to
- parse_evicted_ref_payload: normalize an evicted-output event into a payload with a reference
- find_step_for_evicted: the progress step an evicted payload belongs to
- attach_evicted_to_step: record the evicted reference, preview and size metrics on a step
- step_accepts_pending_evicted: whether a step can take an evicted payload that arrived before it

[POS]
Stateless helpers for stream_collector. Evicted output arrives as its own event, before or after the tool step it
belongs to, so the collector holds it until a step accepts it.
"""

from __future__ import annotations

BASH_EXECUTE_TOOL = "bash_code_execute_tool"
_MAX_EVICTED_PREVIEW_CHARS = 8_000
_EVICTED_STREAM_STDOUT = "stdout"
_EVICTED_STREAM_STDERR = "stderr"
_VALID_EVICTED_STREAMS = frozenset({_EVICTED_STREAM_STDOUT, _EVICTED_STREAM_STDERR})


def _ensure_evicted_stdout_preview(step: dict[str, object]) -> None:
    stdout = step.get("stdout")
    if isinstance(stdout, str) and stdout.strip():
        return
    step["stdout"] = "[LARGE OUTPUT TRUNCATED]\n\n(Full output evicted to workspace file)"


def _cap_evicted_preview(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) > _MAX_EVICTED_PREVIEW_CHARS:
        return text[:_MAX_EVICTED_PREVIEW_CHARS]
    return text


def parse_evicted_ref_payload(
    data: object,
    event: dict[str, object],
) -> dict[str, object] | None:
    payload: dict[str, object] = {}
    if isinstance(data, str) and data.strip():
        payload["evicted_ref"] = data.strip()
    elif isinstance(data, dict):
        raw_ref = data.get("evicted_ref")
        if isinstance(raw_ref, str) and raw_ref.strip():
            payload["evicted_ref"] = raw_ref.strip()
        tool_name = data.get("tool_name")
        if isinstance(tool_name, str) and tool_name.strip():
            payload["tool_name"] = tool_name.strip()
        tool_call_id = data.get("tool_call_id")
        if isinstance(tool_call_id, str) and tool_call_id.strip():
            payload["tool_call_id"] = tool_call_id.strip()
        stream = data.get("stream")
        if isinstance(stream, str) and stream.strip() in _VALID_EVICTED_STREAMS:
            payload["stream"] = stream.strip()
        preview = _cap_evicted_preview(data.get("preview_stdout"))
        if preview:
            payload["preview_stdout"] = preview
        stored_chars = data.get("stored_chars")
        if isinstance(stored_chars, int) and stored_chars > 0:
            payload["stored_chars"] = stored_chars
        total_lines = data.get("total_lines")
        if isinstance(total_lines, int) and total_lines > 0:
            payload["total_lines"] = total_lines
        storage_truncated = data.get("storage_truncated")
        if storage_truncated is True:
            payload["storage_truncated"] = True
    event_tool = event.get("tool_name")
    if isinstance(event_tool, str) and event_tool.strip() and "tool_name" not in payload:
        payload["tool_name"] = event_tool.strip()
    ref = payload.get("evicted_ref")
    return payload if isinstance(ref, str) and ref else None


def _evicted_stream(payload: dict[str, object]) -> str:
    stream = payload.get("stream")
    return stream if stream in _VALID_EVICTED_STREAMS else _EVICTED_STREAM_STDOUT


def _evicted_ref_keys(payload: dict[str, object]) -> tuple[str, str, str, str]:
    if _evicted_stream(payload) == _EVICTED_STREAM_STDERR:
        return (
            "evicted_stderr_file_ref",
            "evicted_stderr_stored_chars",
            "evicted_stderr_total_lines",
            "evicted_stderr_storage_truncated",
        )
    return (
        "evicted_file_ref",
        "evicted_stored_chars",
        "evicted_total_lines",
        "evicted_storage_truncated",
    )


def attach_evicted_to_step(step: dict[str, object], payload: dict[str, object]) -> None:
    ref = payload.get("evicted_ref")
    if not isinstance(ref, str) or not ref:
        return
    is_stderr = _evicted_stream(payload) == _EVICTED_STREAM_STDERR
    ref_key, stored_key, lines_key, truncated_key = _evicted_ref_keys(payload)
    step[ref_key] = ref
    if not is_stderr:
        step["status"] = "success"
        preview = payload.get("preview_stdout")
        if isinstance(preview, str) and preview.strip():
            step["stdout"] = preview
        else:
            _ensure_evicted_stdout_preview(step)
    tool_call_id = payload.get("tool_call_id")
    if isinstance(tool_call_id, str) and tool_call_id.strip() and not step.get("tool_call_id"):
        step["tool_call_id"] = tool_call_id.strip()
    if not step.get("step_key"):
        step_tool = step.get("tool_name")
        if step_tool == BASH_EXECUTE_TOOL:
            step["step_key"] = "bash_code_execute_tool_tool"
        elif isinstance(step_tool, str) and step_tool:
            step["step_key"] = step_tool
    stored_chars = payload.get("stored_chars")
    if isinstance(stored_chars, int) and stored_chars > 0:
        step[stored_key] = stored_chars
    total_lines = payload.get("total_lines")
    if isinstance(total_lines, int) and total_lines > 0:
        step[lines_key] = total_lines
    if payload.get("storage_truncated") is True:
        step[truncated_key] = True


def find_step_for_evicted(
    steps: list[dict[str, object]],
    payload: dict[str, object],
) -> dict[str, object] | None:
    tool_call_id = payload.get("tool_call_id")
    if isinstance(tool_call_id, str) and tool_call_id.strip():
        target_id = tool_call_id.strip()
        for step in reversed(steps):
            if step.get("tool_call_id") == target_id:
                return step
    ref_key = _evicted_ref_keys(payload)[0]
    tool_hint = payload.get("tool_name")
    if isinstance(tool_hint, str) and tool_hint.strip():
        for step in reversed(steps):
            if step.get(ref_key):
                continue
            if step.get("tool_name") == tool_hint.strip():
                return step
    for step in reversed(steps):
        if step.get(ref_key):
            continue
        if step.get("tool_name") == BASH_EXECUTE_TOOL:
            return step
    return None


def step_accepts_pending_evicted(step: dict[str, object], payload: dict[str, object]) -> bool:
    tool_call_id = payload.get("tool_call_id")
    if isinstance(tool_call_id, str) and tool_call_id.strip():
        return step.get("tool_call_id") == tool_call_id.strip()
    tool_hint = payload.get("tool_name")
    step_tool = step.get("tool_name")
    if isinstance(tool_hint, str) and tool_hint:
        return step_tool == tool_hint
    if step_tool == BASH_EXECUTE_TOOL:
        return True
    step_key = step.get("step_key")
    return isinstance(step_key, str) and step_key.startswith("bash_code_execute_tool")
