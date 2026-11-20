"""The files a file tool call is judged on: every spelling the tool may open, not only the one that was typed.

[INPUT]
- core.security.path::find_existing_unicode_path (POS: the spelling a read opens in place of a typed one that names no file)
- core.security.tool_registry::host_file_paths (POS: the host files a call names, in every form a reader could open them)

[OUTPUT]
- judged_file_paths(permission, tool_input, workspace_root) -> list[str]: the typed host files, then the spelling a read opens in place of each

[POS]
Target set of the permission engine's rule matching and zone check for file tools and of the directory grants an approval plans and opens: a superset of the files the tool can open, so a respelling can only tighten a verdict, and what an approval opens is what the tool opens.
"""

from __future__ import annotations

from myrm_agent_harness.core.security.path import find_existing_unicode_path
from myrm_agent_harness.core.security.tool_registry import host_file_paths


def judged_file_paths(permission: str, tool_input: dict[str, object], workspace_root: str | None) -> list[str]:
    """The host files a call names and, for a read, the spelling it opens in place of one that names no file.

    ``file_read`` opens the respelling of a typed path that names nothing (``find_existing_unicode_path``), so rules
    and zones must judge that file too: a quote, a backtick or a decomposed accent would otherwise be enough to read a
    file the typed text keeps out of reach. Every other file tool opens exactly the path it is given.
    """
    paths = host_file_paths(tool_input)
    if permission != "file_read":
        return paths
    respelled = (find_existing_unicode_path(path, workspace_root) for path in paths)
    return list(dict.fromkeys([*paths, *filter(None, respelled)]))
