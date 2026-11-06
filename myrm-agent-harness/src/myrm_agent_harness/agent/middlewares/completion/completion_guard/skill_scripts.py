"""Saved skill scripts: scripts the run saved to a file that call an MCP skill, as the verification checklist sees them.

[INPUT]
- agent.meta_tools.file_ops.core.file_edit_normalizer::normalize_edits_payload (POS: the edits a ``file_edit_tool`` call carries)
- agent.middlewares.completion.completion_guard.verification::imports_mcp_skill, script_runs (POS: what a script's text and a command line say)
- agent.security.guards.loop_guard::CallRecord (POS: the recorded call)

[OUTPUT]
- without_skill_scripts(): the records minus saved MCP skill scripts, the edits to them and the runs of them

[POS]
A script that imports an MCP skill is a tool call like the inline ones ``classify_verification`` leaves out, but a
saved one only runs as ``python file.py``, so nothing in the run command says what it calls. The file's content is
read from the run's own write records, and the write, the edits to it and the runs after it leave the records the
checklist judges: the write is not code that needs a test run, its pass proves nothing about other code, and its
failure says nothing once the data came another way.
"""

from __future__ import annotations

import posixpath
from collections.abc import Sequence

from myrm_agent_harness.agent.meta_tools.file_ops.core.file_edit_normalizer import normalize_edits_payload
from myrm_agent_harness.agent.middlewares.completion.completion_guard.verification import (
    imports_mcp_skill,
    script_runs,
)
from myrm_agent_harness.agent.security.guards.loop_guard import CallRecord

_FILE_WRITE_TOOL = "file_write_tool"
_FILE_EDIT_TOOL = "file_edit_tool"
_BASH_TOOL = "bash_code_execute_tool"


def _same_file(written: str, directory: str | None, script: str) -> bool:
    """Whether ``python script`` (after ``cd directory``) runs the file ``written``.

    A path given without its root (the model's relative name, a container path) is the same file as an absolute one
    that ends with it.
    """
    ran = posixpath.normpath(posixpath.join(directory, script) if directory else script)
    saved = posixpath.normpath(written)
    if ran == saved:
        return True
    if ran.startswith("/") != saved.startswith("/"):
        absolute, relative = (ran, saved) if ran.startswith("/") else (saved, ran)
        return absolute.endswith(f"/{relative}")
    return False


def _is_saved(skill_files: set[str], path: str) -> bool:
    return any(_same_file(saved, None, path) for saved in skill_files)


def _forget(skill_files: set[str], path: str) -> set[str]:
    return {saved for saved in skill_files if not _same_file(saved, None, path)}


def _edit_drops_skill_import(args: dict[str, object]) -> bool:
    """Whether an edit replaces text that imports a skill with text that does not.

    The edit shows only the text it replaces, so this is the one change it can show to turn a skill script into
    plain code. An edit that cannot be read is a failed call and changes nothing.
    """
    try:
        edits = normalize_edits_payload(args)
    except ValueError:
        return False
    return any(imports_mcp_skill(edit["old_str"]) and not imports_mcp_skill(edit["new_str"]) for edit in edits)


def without_skill_scripts(records: Sequence[CallRecord]) -> list[CallRecord]:
    """The records the verification checklist judges: no saved MCP skill script, edit of one, or run of one.

    A file counts from the write that gave it a skill import until a write or edit that took it out; only the
    edits and runs in between are dropped.
    """
    skill_files: set[str] = set()
    kept: list[CallRecord] = []
    for record in records:
        path = str(record.args.get("path", ""))
        if record.tool_name == _FILE_WRITE_TOOL and path.endswith(".py"):
            if imports_mcp_skill(str(record.args.get("content", ""))):
                skill_files.add(path)
                continue
            skill_files = _forget(skill_files, path)
        elif record.tool_name == _FILE_EDIT_TOOL and _is_saved(skill_files, path):
            if not _edit_drops_skill_import(record.args):
                continue
            skill_files = _forget(skill_files, path)
        elif skill_files and record.tool_name == _BASH_TOOL:
            runs = script_runs(str(record.args.get("command", "")))
            if any(_same_file(saved, directory, script) for directory, script in runs for saved in skill_files):
                continue
        kept.append(record)
    return kept


__all__ = ["without_skill_scripts"]
