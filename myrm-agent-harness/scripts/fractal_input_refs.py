"""Resolvability of the ``[INPUT]`` references in harness file headers.

A header lists what a module reads as ``dotted.module::Symbol (POS: ...)``. The line is
documentation: after a move, a rename or a deletion it points at a file that is gone and
sends the reader, human or agent, to nothing. This check resolves the module part of every
reference against the files on disk. There is no baseline and no per-reference allowlist:
point the reference at the module's real location, or delete the line once the dependency
is gone.

Only first-party references are checked, so stdlib and third-party ones need no allowlist:
a reference is first-party when its first segment names a directory or a module somewhere
in the package. Headers abbreviate the leading packages (``cost_engine`` and
``token_economics.cost_engine`` both stand for ``utils/token_economics/cost_engine.py``), so
a reference resolves when its dotted path, minus leading dots and an optional package name,
is a suffix of the dotted path of a real module or directory; ``utils.cost_engine`` is not.
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

# Third-party packages whose import name is also a first-party directory (``toolkits/mcp``,
# ``toolkits/acp``): an unresolved reference under these names may name the SDK, which no
# static check without the installed packages can tell apart.
_SHADOWED_THIRD_PARTY_ROOTS: frozenset[str] = frozenset({"acp", "mcp"})

_INPUT_START = re.compile(r"^\s*\[INPUT\]")
_INPUT_END = re.compile(r"^\s*\[(?:OUTPUT|POS)\]|\"\"\"|'''")
_REFERENCE = re.compile(r"^\s*(?:[-*]\s+)?(\.*[A-Za-z_]\w*(?:\.\w+)*)::")


@dataclass(frozen=True, slots=True)
class DanglingReference:
    """One ``[INPUT]`` reference whose module does not exist."""

    path: Path
    line: int
    target: str


class _ModuleIndex:
    """Every module and directory of a package as a dotted path relative to its root."""

    def __init__(self, package_root: Path, pruned_dirs: frozenset[str]) -> None:
        paths: set[str] = set()
        python_files: list[Path] = []
        for directory, subdirs, files in os.walk(package_root):
            subdirs[:] = [name for name in subdirs if name not in pruned_dirs]
            parts = Path(directory).relative_to(package_root).parts
            if parts:
                paths.add(".".join(parts))
            for name in files:
                if name.endswith(".py"):
                    python_files.append(Path(directory, name))
                    if name != "__init__.py":
                        paths.add(".".join((*parts, name.removesuffix(".py"))))

        suffixes: set[str] = set()
        segments: set[str] = set()
        for path in paths:
            parts = tuple(path.split("."))
            segments.update(parts)
            suffixes.update(".".join(parts[start:]) for start in range(len(parts)))

        self.python_files = tuple(sorted(python_files))
        self._package_prefix = f"{package_root.name}."
        self._suffixes = frozenset(suffixes)
        self._segments = frozenset(segments)

    def resolves(self, target: str) -> bool:
        """Whether ``target`` names a module of the package, or lies outside it (stdlib, third party)."""
        dotted = target.lstrip(".").removeprefix(self._package_prefix)
        if dotted in self._suffixes:
            return True
        head = dotted.partition(".")[0]
        return head not in self._segments or head in sys.stdlib_module_names or head in _SHADOWED_THIRD_PARTY_ROOTS


def _input_references(path: Path, header_lines: int) -> Iterator[tuple[int, str]]:
    """Yield ``(line, target)`` for each ``target::Symbol`` line of the file's ``[INPUT]`` block.

    The block must open within the first ``header_lines`` lines; it ends at ``[OUTPUT]``,
    ``[POS]`` or the closing quotes of the header docstring.
    """
    in_block = False
    with path.open(encoding="utf-8", errors="replace") as handle:
        for number, line in enumerate(handle, start=1):
            if not in_block:
                if number > header_lines:
                    return
                in_block = _INPUT_START.match(line) is not None
            elif _INPUT_END.search(line):
                return
            elif match := _REFERENCE.match(line):
                yield number, match.group(1)


def dangling_input_references(
    package_root: Path, *, pruned_dirs: frozenset[str], header_lines: int
) -> list[DanglingReference]:
    """Every ``[INPUT]`` reference of the package whose module does not exist, in path order."""
    index = _ModuleIndex(package_root, pruned_dirs)
    return [
        DanglingReference(file, line, target)
        for file in index.python_files
        for line, target in _input_references(file, header_lines)
        if not index.resolves(target)
    ]
