"""Path arguments of the file tools: the one place that says which arguments carry files.

[INPUT]
- (none — pure functions over tool-call argument dicts)

[OUTPUT]
- FILE_ARG_KEYS: every argument name a file tool receives its files under
- PATHS_ALIAS_KEYS: the single-path spellings ``file_read_tool`` accepts for its ``paths`` list
- coerce_path_list: a path argument as a list, reading a string that holds a JSON array the way the tool does
- file_arg_values: each non-empty path string among those arguments, passed as a string, a JSON array string or a list
- strip_read_range: a path without its ``:START-END`` line-range selector
- is_url: whether a path is a network URL, which file tools refuse
- host_file_paths: the host-filesystem paths a call may open, in every form the reader could open them

[POS]
Shared by the permission engine (path-zone verdict and rule targets), the session directory grant, the
approval-hash canonical parameters and the taint extractors, so that a path sent under any spelling is
judged the same way everywhere.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator

# ``file_read_tool`` batches its files in a ``paths`` list and accepts every single-path spelling below as an alias,
# so models send any of them.
FILE_ARG_KEYS: tuple[str, ...] = (
    "path",
    "paths",
    "file_path",
    "filePath",
    "filepath",
    "file",
    "files",
    "filename",
    "target",
    "target_file",
    "source_file",
    "path_list",
)

# The subset of the spellings above that ``file_read_tool`` folds into its ``paths`` list. Every one must stay in
# ``FILE_ARG_KEYS``: a file the tool opens under a name the verdict does not read would never be judged.
PATHS_ALIAS_KEYS: tuple[str, ...] = (
    "filePath",
    "file_path",
    "path",
    "file",
    "files",
    "filename",
    "target",
    "path_list",
)

_URL_SCHEMES = ("http://", "https://", "ftp://", "ftps://")

# Namespaces the read tool serves itself and that name no host file: MCP skill documents and Artifact Vault pointers.
_VIRTUAL_PREFIXES = ("/mcp/", "vault://")

# ``path:START-END`` line-range selector that file_read_tool accepts after the file name.
_READ_RANGE_SUFFIX_RE = re.compile(r":\d+-\d*$")


def coerce_path_list(value: object) -> list[object] | None:
    """A path argument as a list: a list stays one, a string holding a JSON array becomes that array, any other
    string is a single path, and anything else is not a path argument.

    Models often send an array argument as its JSON text. The tool reads it as the array, so every judgement of
    the call must read it the same way: the paths inside are the files that get opened.
    """
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (ValueError, RecursionError):
            return [value]
        return parsed if isinstance(parsed, list) else [value]
    return None


def file_arg_values(args: dict[str, object]) -> Iterator[str]:
    """Yield every non-empty path string in the arguments, whether passed as a string, a JSON array string or a list."""
    for key in FILE_ARG_KEYS:
        for item in coerce_path_list(args.get(key)) or ():
            if isinstance(item, str) and item.strip():
                yield item.strip()


def strip_read_range(path: str) -> str:
    """The path without a trailing ``:START-END`` line-range selector."""
    return _READ_RANGE_SUFFIX_RE.sub("", path)


def is_url(path: str) -> bool:
    """Whether the path is a network URL (http, https, ftp, ftps)."""
    return path.lower().startswith(_URL_SCHEMES)


def host_file_paths(args: dict[str, object]) -> list[str]:
    """The host-filesystem paths the arguments may open, each in every form the reader could open it.

    URLs and the virtual namespaces name no host file and are left out. The reader opens a path without its
    line range and cuts it at the first colon, so a path is returned in both forms and a verdict can be taken
    on each: a path must not pass for what it looks like as a whole while opening something else.
    """
    paths: list[str] = []
    for raw in file_arg_values(args):
        if is_url(raw) or raw.startswith(_VIRTUAL_PREFIXES):
            continue
        for candidate in (strip_read_range(raw), raw.split(":", 1)[0]):
            if candidate and candidate not in paths:
                paths.append(candidate)
    return paths
