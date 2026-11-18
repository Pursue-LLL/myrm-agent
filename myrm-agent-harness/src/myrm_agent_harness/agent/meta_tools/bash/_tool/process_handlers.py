"""Action handlers of ``bash_process_tool``: list, output, wait, kill and stdin on a session's background jobs.

[INPUT]
- agent.meta_tools.bash._background.registry::get_background_registry (POS: registry singleton)
- agent.meta_tools.bash._background.termination::GROUP_VISIBLE (POS: whether the platform can list a job's process group)
- agent.meta_tools.bash._background.types::build_input_wait_hint (POS: shared dataclasses & typing.)

[OUTPUT]
- OUTPUT_DEFAULT_LINES: default tail size per stream
- handle_list / handle_output / handle_wait / handle_kill / handle_stdin: one coroutine per action, each returning the tool payload ``{content, metadata}``; ``list``, ``output`` and ``wait`` name what a finished job left running (``leftover_processes``, present only when above zero)
- kill_report: the text a kill returns to the model, stating what the stop actually achieved

[POS]
Session-scoped handlers behind the ``bash_process_tool`` facade, which owns the schema, the capability gate and the dispatch.
"""

from __future__ import annotations

from myrm_agent_harness.agent.meta_tools.bash._background.registry import (
    get_background_registry,
)
from myrm_agent_harness.agent.meta_tools.bash._background.termination import GROUP_VISIBLE
from myrm_agent_harness.agent.meta_tools.bash._background.types import (
    build_input_wait_hint,
)

OUTPUT_DEFAULT_LINES = 100

# A process that started its own session is out of the job's reach, so a stop cannot vouch for it.
_NONE_FOUND = "no process it started was found still running (programs that detached themselves are not tracked)"


async def handle_list(session_id: str) -> dict[str, object]:
    registry = get_background_registry()
    items = registry.list_processes(session_id=session_id)
    return {
        "content": {
            "processes": [i.to_dict() for i in items],
            "count": len(items),
        },
        "metadata": {"session_id": session_id, "action": "list"},
    }


async def handle_output(session_id: str, pid: int, max_lines: int) -> dict[str, object]:
    registry = get_background_registry()
    info = registry.get(pid)
    if info is None or info.session_id != session_id:
        return {
            "content": f"No background process with pid={pid} in this session.",
            "metadata": {"pid": pid, "found": False, "action": "output"},
        }

    streams = registry.get_output(pid, max_lines=max_lines)
    content: dict[str, object] = {
        "pid": pid,
        "status": info.status,
        "exit_code": info.exit_code,
        "error_category": info.error_category,
        "stdout": streams["stdout"],
        "stderr": streams["stderr"],
        "dropped": streams["dropped"],
    }
    spill_log_ref = streams.get("spill_log_ref")
    if spill_log_ref:
        content["spill_log_ref"] = spill_log_ref
    if info.leftover_processes:
        content["leftover_processes"] = info.leftover_processes
    if info.status == "running":
        content["waiting_for_input"] = info.waiting_for_input
        content["last_output_at"] = info.last_output_at
        hint = build_input_wait_hint(info)
        if hint:
            content["input_wait_hint"] = hint

    return {
        "content": content,
        "metadata": {"pid": pid, "session_id": session_id, "action": "output"},
    }


async def handle_wait(session_id: str, pid: int, timeout_seconds: int) -> dict[str, object]:
    registry = get_background_registry()
    info = registry.get(pid)
    if info is None or info.session_id != session_id:
        return {
            "content": f"No background process with pid={pid} in this session.",
            "metadata": {"pid": pid, "found": False, "action": "wait"},
        }
    result = await registry.wait_for_process(pid, timeout_seconds=float(timeout_seconds))
    still_running = bool(result.get("still_running"))
    content: dict[str, object] = {
        "pid": pid,
        "still_running": still_running,
        "status": result.get("status"),
        "exit_code": result.get("exit_code"),
        "error_category": result.get("error_category"),
    }
    if still_running:
        live = registry.get(pid)
        content["message"] = f"pid={pid} still running after {timeout_seconds}s; poll with action=output or wait again."
        if live is not None and live.status == "running":
            content["waiting_for_input"] = live.waiting_for_input
            content["last_output_at"] = live.last_output_at
            hint = build_input_wait_hint(live)
            if hint:
                content["input_wait_hint"] = hint
    else:
        streams = registry.get_output(pid, max_lines=OUTPUT_DEFAULT_LINES)
        content["stdout"] = streams["stdout"]
        content["stderr"] = streams["stderr"]
        # The job may have finished during the wait, so what it left running is read now, not from the first snapshot.
        finished = registry.get(pid)
        if finished is not None and finished.leftover_processes:
            content["leftover_processes"] = finished.leftover_processes
    return {
        "content": content,
        "metadata": {
            "pid": pid,
            "session_id": session_id,
            "action": "wait",
            "still_running": still_running,
        },
    }


async def handle_kill(session_id: str, pid: int, force: bool) -> dict[str, object]:
    registry = get_background_registry()
    info = registry.get(pid)
    if info is None or info.session_id != session_id:
        return {
            "content": f"No background process with pid={pid} in this session.",
            "metadata": {"pid": pid, "found": False, "action": "kill"},
        }
    was_running = info.status == "running"
    left_before = info.leftover_processes
    ok = await registry.kill(pid, force=force)
    after = registry.get(pid)
    leftover = after.leftover_processes if after is not None else 0
    return {
        "content": kill_report(
            pid,
            force=force,
            ok=ok,
            was_running=was_running,
            left_before=left_before,
            leftover=leftover,
            group_visible=GROUP_VISIBLE,
        ),
        "metadata": {
            "pid": pid,
            "force": force,
            "killed": ok,
            "leftover_processes": leftover,
            "session_id": session_id,
            "action": "kill",
        },
    }


def kill_report(
    pid: int,
    *,
    force: bool,
    ok: bool,
    was_running: bool,
    left_before: int,
    leftover: int,
    group_visible: bool,
) -> str:
    """What a stop found: processes it started that are still running are reported, not assumed gone.

    Where the platform cannot list a job's group (``group_visible`` is false) the report says only what was sent.
    """
    if not ok:
        return f"Failed to signal pid={pid}"
    sent = "SIGKILL" if force else "SIGTERM"
    if leftover:
        # A graceful stop escalates to SIGKILL by itself, so what is still running outlived SIGKILL too.
        signals = "SIGKILL" if force else "SIGTERM then SIGKILL"
        return f"Sent {signals} to pid={pid}, but {leftover} process(es) it started are still running."
    if was_running:
        return f"Stopped pid={pid}; {_NONE_FOUND}." if group_visible else f"Sent {sent} to pid={pid}"
    if left_before:
        return f"pid={pid} had already finished; stopped the {left_before} process(es) it left running."
    return f"pid={pid} had already finished and {_NONE_FOUND}." if group_visible else f"pid={pid} had already finished."


async def handle_stdin(
    session_id: str,
    pid: int,
    data: str,
    *,
    append_newline: bool,
    close: bool,
    action: str,
) -> dict[str, object]:
    registry = get_background_registry()
    info = registry.get(pid)
    if info is None or info.session_id != session_id:
        return {
            "content": f"No background process with pid={pid} in this session.",
            "metadata": {"pid": pid, "found": False, "action": action},
        }
    result = await registry.write_stdin(
        pid,
        data,
        append_newline=append_newline,
        close=close,
    )
    ok = bool(result.get("ok"))
    return {
        "content": result,
        "metadata": {
            "pid": pid,
            "session_id": session_id,
            "action": action,
            "ok": ok,
        },
    }


__all__ = [
    "OUTPUT_DEFAULT_LINES",
    "handle_kill",
    "handle_list",
    "handle_output",
    "handle_stdin",
    "handle_wait",
    "kill_report",
]
