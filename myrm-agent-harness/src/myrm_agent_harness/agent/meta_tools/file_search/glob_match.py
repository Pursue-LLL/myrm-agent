"""Shared glob semantics for the file search tools.

[INPUT]
- glob::translate (POS: stdlib glob → regular-expression compiler, ``**`` aware)
- regex (POS: third-party regular-expression engine; matches stacked wildcards without catastrophic backtracking)

[OUTPUT]
- compile_glob: Validate a user-supplied glob and compile it into a regular expression
- glob_matches: Test one root-relative POSIX path against a glob
- is_match_all: Whether a glob selects every file (so no filter is needed)
- normalize_glob: The spelling both ripgrep's ``--glob`` and the matcher read the same way

[POS]
Single definition of what a ``pattern`` / ``file_pattern`` means for ``glob_tool`` and ``grep_tool``,
shared by the ripgrep tier and the Python tier so a pattern selects the same paths on both. The dialect matches
ripgrep's ``--glob`` for file paths: a pattern without ``/`` matches at any depth, a pattern containing
``/`` is anchored at the search root, ``**`` crosses directories, ``{a,b}`` expands, and ``*`` matches
dot-files (hidden-file policy is applied by the caller, never by the pattern). Matching runs on the server's
event loop, so the compiled expression uses the ``regex`` engine: with the standard library's ``re``,
``**/a/**/a/**/a/**/a/**/b`` against a 127-level path takes seconds, here it takes about a millisecond.
"""

from __future__ import annotations

import glob
import re
from functools import lru_cache

import regex

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


def normalize_glob(pattern: str) -> str:
    """Spell ``pattern`` the way ripgrep's ``--glob`` and :func:`compile_glob` both read it.

    Surrounding blanks and a leading ``./`` carry no meaning for either, but ripgrep would take ``./src/*.py``
    literally and match nothing.
    """
    return pattern.strip().removeprefix("./")


@lru_cache(maxsize=256)
def compile_glob(pattern: str) -> regex.Pattern[str]:
    """Compile ``pattern`` for :func:`glob_matches`.

    Raises:
        ValueError: The pattern is empty, contains a NUL byte, or expands to too many alternatives.
    """
    if "\x00" in pattern:
        raise ValueError("NUL byte is not allowed in glob patterns")
    normalized = normalize_glob(pattern)
    if not normalized:
        raise ValueError("empty pattern")
    regexes = [_alternative_to_regex(alternative) for alternative in _expand_braces(normalized)]
    return regex.compile("|".join(f"(?:{translated})" for translated in regexes))


def glob_matches(relative_posix_path: str, pattern: str) -> bool:
    """Return whether a root-relative POSIX path (``/`` separators) matches ``pattern``."""
    return compile_glob(pattern).fullmatch(relative_posix_path) is not None


def is_match_all(pattern: str) -> bool:
    """Return whether ``pattern`` selects every file, so callers can skip filtering entirely."""
    return normalize_glob(pattern) in _MATCH_ALL_PATTERNS
