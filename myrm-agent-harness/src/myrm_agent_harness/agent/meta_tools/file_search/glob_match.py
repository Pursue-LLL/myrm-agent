"""Shared glob semantics for the file search tools.

[INPUT]
- glob::translate (POS: stdlib glob → regular-expression compiler, ``**`` aware)

[OUTPUT]
- compile_glob: Validate a user-supplied glob and compile it into a regular expression
- glob_matches: Test one root-relative POSIX path against a glob
- is_match_all: Whether a glob selects every file (so no filter is needed)

[POS]
Single definition of what a ``pattern`` / ``file_pattern`` means for ``glob_tool`` and ``grep_tool``,
shared by the ripgrep tier and the Python tier so both return the same files. The dialect matches
ripgrep's ``--glob`` for file paths: a pattern without ``/`` matches at any depth, a pattern containing
``/`` is anchored at the search root, ``**`` crosses directories, ``{a,b}`` expands, and ``*`` matches
dot-files (hidden-file policy is applied by the caller, never by the pattern).
"""

from __future__ import annotations

import glob
import re
from functools import lru_cache

# ``{a,b}{c,d}...`` multiplies; bound the expansion so a hostile pattern cannot blow up compilation.
_MAX_BRACE_ALTERNATIVES = 128

_MATCH_ALL_PATTERNS = frozenset({"*", "**", "**/*", "**/**"})

_INNERMOST_BRACE = re.compile(r"\{([^{}]*)\}")


def _first_alternation(text: str) -> re.Match[str] | None:
    """Return the first innermost ``{a,b}`` group; a group without a comma is literal text."""
    return next((m for m in _INNERMOST_BRACE.finditer(text) if "," in m.group(1)), None)


def _expand_braces(pattern: str) -> list[str]:
    """Expand ``{a,b}`` groups, nesting included."""
    pending = [pattern]
    expanded: list[str] = []
    while pending:
        current = pending.pop()
        match = _first_alternation(current)
        if match is None:
            expanded.append(current)
            continue
        head, tail = current[: match.start()], current[match.end() :]
        pending.extend(f"{head}{alternative}{tail}" for alternative in match.group(1).split(","))
        if len(pending) + len(expanded) > _MAX_BRACE_ALTERNATIVES:
            raise ValueError(f"too many brace alternatives (limit {_MAX_BRACE_ALTERNATIVES})")
    return expanded


def _alternative_to_regex(alternative: str) -> str:
    anchored = alternative.startswith("/")
    body = alternative.lstrip("/")
    if not body:
        raise ValueError("empty pattern")
    if not anchored and "/" not in body:
        body = f"**/{body}"
    return glob.translate(body, recursive=True, include_hidden=True, seps="/")


@lru_cache(maxsize=256)
def compile_glob(pattern: str) -> re.Pattern[str]:
    """Compile ``pattern`` for :func:`glob_matches`.

    Raises:
        ValueError: The pattern is empty, contains a NUL byte, or expands to too many alternatives.
    """
    if "\x00" in pattern:
        raise ValueError("NUL byte is not allowed in glob patterns")
    normalized = pattern.strip().removeprefix("./")
    if not normalized:
        raise ValueError("empty pattern")
    regexes = [_alternative_to_regex(alternative) for alternative in _expand_braces(normalized)]
    return re.compile("|".join(f"(?:{regex})" for regex in regexes))


def glob_matches(relative_posix_path: str, pattern: str) -> bool:
    """Return whether a root-relative POSIX path (``/`` separators) matches ``pattern``."""
    return compile_glob(pattern).fullmatch(relative_posix_path) is not None


def is_match_all(pattern: str) -> bool:
    """Return whether ``pattern`` selects every file, so callers can skip filtering entirely."""
    return pattern.strip().removeprefix("./") in _MATCH_ALL_PATTERNS
