"""Path arguments of the file tools: the one place that says which arguments carry files.

[INPUT]
- (none — pure functions over tool-call argument dicts)

[OUTPUT]
- FILE_ARG_KEYS: every argument name a file tool receives its files under
- PATHS_ALIAS_KEYS: the single-path spellings ``file_read_tool`` accepts for its ``paths`` list
- coerce_path_list: an array argument as a list, reading a string that holds a JSON array the way the tool does (``url_args`` reads ``urls`` with it too)
- file_arg_values: each non-empty path string among those arguments, passed as a string, a JSON array string or a list
- READ_RANGE_PATTERN: the one grammar of the ``:START-END`` line-range selector after a file name (groups: file, start, end)
- strip_read_range: the file a path argument names: the path without its ``:START-END`` line-range selector
- is_url: whether a path is a network URL, which file tools refuse
- host_file_paths: the host-filesystem paths a call may open, in every form a reader could open them

[POS]
Shared by the permission engine (path-zone verdict and rule targets), the session directory grant, the
approval-hash canonical parameters and the taint extractors, so that a path sent under any spelling is
judged the same way everywhere. The file tools parse a range with the same ``READ_RANGE_PATTERN`` that the
verdict strips it with, so the file a read opens is the file the verdict judged.
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

# The line-range selector ``file_read_tool`` takes after a file name: ``path:START-END`` or ``path:START-``. Only that
# trailing form is a range; every other colon (a drive letter, ``notes:v2.md``) belongs to the file name.
READ_RANGE_PATTERN = re.compile(r"^(.+):(\d+)-(\d*)$")


def coerce_path_list(value: object) -> list[object] | None:
    """A path (or URL) argument as a list: a list stays one, a string holding a JSON array becomes that array, any
    other string is a single path, and anything else is not a path argument.

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
    """The file a path argument names: the path without a trailing ``:START-END`` line-range selector.

    Nothing is validated and no file id is resolved, so it is safe on any text; the file tools parse the range's
    numbers with the same ``READ_RANGE_PATTERN``.
    """
    match = READ_RANGE_PATTERN.match(path)
    return match.group(1) if match else path


def is_url(path: str) -> bool:
    """Whether the path is a network URL (http, https, ftp, ftps)."""
    return path.lower().startswith(_URL_SCHEMES)


def host_file_paths(args: dict[str, object]) -> list[str]:
    """The host-filesystem paths the arguments may open, each in every form a reader could open it.

    URLs and the virtual namespaces name no host file and are left out. ``file_read_tool`` opens a path without
    its trailing line range; the form cut at the first colon is returned too, so that a reader that stops at a
    colon cannot open a file the verdict never saw.
    """
    paths: list[str] = []
    for raw in file_arg_values(args):
        if is_url(raw) or raw.startswith(_VIRTUAL_PREFIXES):
            continue
        for candidate in (strip_read_range(raw), raw.split(":", 1)[0]):
            if candidate and candidate not in paths:
                paths.append(candidate)
    return paths
