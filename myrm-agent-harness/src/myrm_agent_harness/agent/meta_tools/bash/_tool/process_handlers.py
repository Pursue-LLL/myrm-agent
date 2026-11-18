"""Action handlers of ``bash_process_tool``: list, output, wait, kill and stdin on a session's background jobs.

[INPUT]
- agent.context_management.infra.evicted::evicted_rel_path (POS: where an evicted file lives; names the log of a listed job)
- agent.meta_tools.bash._background.registry::BackgroundProcessRegistry / get_background_registry (POS: registry singleton; ``get_partial_line`` is the unfinished last line of a running job)
- agent.meta_tools.bash._background.termination::GROUP_VISIBLE (POS: whether the platform can list a job's process group)
- agent.meta_tools.bash._background.types::BackgroundProcessInfo / OutputTail / build_input_wait_hint (POS: shared dataclasses & typing.)

[OUTPUT]
- OUTPUT_DEFAULT_LINES: default tail size per stream
- handle_list / handle_output / handle_wait / handle_kill / handle_stdin: one coroutine per action, each returning the tool payload ``{content, metadata}``; ``output`` and a finished ``wait`` carry the same output fields (both streams, ``dropped``, ``log_file`` when lines are missing and the job has a log), ``list`` names each job's ``log_file``; ``output`` and a ``wait`` that times out on a running job add the idle flag with its note and, when the job has printed text without a newline, ``partial_line``; ``list``, ``output`` and ``wait`` name what a finished job left running (``leftover_processes``, present only when above zero)
- kill_report: the text a kill returns to the model, stating what the stop actually achieved

[POS]
Session-scoped handlers behind the ``bash_process_tool`` facade, which owns the schema, the capability gate and the dispatch.
"""

from __future__ import annotations

from myrm_agent_harness.agent.context_management.infra.evicted import evicted_rel_path
from myrm_agent_harness.agent.meta_tools.bash._background.registry import (
    BackgroundProcessRegistry,
    get_background_registry,
)
from myrm_agent_harness.agent.meta_tools.bash._background.termination import GROUP_VISIBLE
from myrm_agent_harness.agent.meta_tools.bash._background.types import (
    BackgroundProcessInfo,
    OutputTail,
    build_input_wait_hint,
)

OUTPUT_DEFAULT_LINES = 100

# A process that started its own session is out of the job's reach, so a stop cannot vouch for it.
_NONE_FOUND = "no process it started was found still running (programs that detached themselves are not tracked)"


def _stream_fields(streams: OutputTail) -> dict[str, object]:
    """What a read of a job's output adds to a result: both streams, whether older lines are missing, the log with them."""
    fields: dict[str, object] = {
        "stdout": streams["stdout"],
        "stderr": streams["stderr"],
        "dropped": streams["dropped"],
    }
    log_file = streams.get("log_file")
    if log_file:
        fields["log_file"] = log_file
    return fields


def _running_fields(registry: BackgroundProcessRegistry, info: BackgroundProcessInfo) -> dict[str, object]:
    """What a read of a running job adds: the idle flag, the unfinished last line when there is one, and the note on the flag."""
    fields: dict[str, object] = {"waiting_for_input": info.waiting_for_input, "last_output_at": info.last_output_at}
    partial_line = registry.get_partial_line(info.pid)
    if partial_line:
        fields["partial_line"] = partial_line
    hint = build_input_wait_hint(info)
    if hint:
        fields["input_wait_hint"] = hint
    return fields


def _listed(info: BackgroundProcessInfo) -> dict[str, object]:
    """One job as ``list`` shows it: its state, and the log of its output once it has one."""
    row = info.to_dict()
    if info.session_id and info.vault_log_ref:
        row["log_file"] = evicted_rel_path(info.session_id, info.vault_log_ref)
    return row


async def handle_list(session_id: str) -> dict[str, object]:
    registry = get_background_registry()
    items = registry.list_processes(session_id=session_id)
    return {
        "content": {
            "processes": [_listed(i) for i in items],
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

    content: dict[str, object] = {
        "pid": pid,
        "status": info.status,
        "exit_code": info.exit_code,
        "error_category": info.error_category,
    }
    content.update(_stream_fields(registry.get_output(pid, max_lines=max_lines)))
    if info.leftover_processes:
        content["leftover_processes"] = info.leftover_processes
    if info.status == "running":
        content.update(_running_fields(registry, info))

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
            content.update(_running_fields(registry, live))
    else:
        content.update(_stream_fields(registry.get_output(pid, max_lines=OUTPUT_DEFAULT_LINES)))
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
