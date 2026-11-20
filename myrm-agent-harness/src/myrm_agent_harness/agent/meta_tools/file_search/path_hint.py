"""Similar-path hints when a requested file or directory is not found.

[INPUT]
- core.security.path (POS: Aggregation facade for the path security domain)

[OUTPUT]
- levenshtein_distance_bounded: Bounded Levenshtein edit distance computation (<= max_dist).
- suggest_similar_paths: Return closest paths under parent dirs using Levenshtein-2 and similarity.
- format_path_not_found_hint: Format informative error message with 'Did you mean' suggestions.
- mcp_namespace_error: Error text for a glob/grep aimed at the virtual /mcp skill-doc namespace.

[POS]
File-search and file-ops UX helper for mistyped or moved workspace paths.
"""

from __future__ import annotations

import os
from difflib import SequenceMatcher, get_close_matches
from pathlib import Path

from myrm_agent_harness.core.security.path import is_blocked_device_path

_MCP_NAMESPACE = "/mcp"


def levenshtein_distance_bounded(s1: str, s2: str, max_dist: int = 2) -> int:
    """Compute Levenshtein edit distance between s1 and s2 with early boundary cutoff.

    Returns the edit distance, or `max_dist + 1` as soon as it is proven that
    distance exceeds `max_dist`.
    """
    len1, len2 = len(s1), len(s2)
    if abs(len1 - len2) > max_dist:
        return max_dist + 1

    if len1 > len2:
        s1, s2 = s2, s1
        len1, len2 = len2, len1

    prev = list(range(len1 + 1))
    for i2, c2 in enumerate(s2, 1):
        curr = [i2] * (len1 + 1)
        min_in_row = curr[0]
        for i1, c1 in enumerate(s1, 1):
            cost = 0 if c1 == c2 else 1
            curr[i1] = min(
                curr[i1 - 1] + 1,
                prev[i1] + 1,
                prev[i1 - 1] + cost,
            )
            if curr[i1] < min_in_row:
                min_in_row = curr[i1]
        if min_in_row > max_dist:
            return max_dist + 1
        prev = curr

    return prev[len1]


def suggest_similar_paths(
    target_path: str,
    *,
    max_suggestions: int = 3,
) -> list[str]:
    """Return up to ``max_suggestions`` paths similar to ``target_path``.

    Uses Bounded Levenshtein-2 ranking on basenames in parent and grandparent
    directories, with fallback to SequenceMatcher for fuzzy similarity.
    """
    norm = os.path.normpath(target_path)
    parent = os.path.dirname(norm) or "."
    basename = os.path.basename(norm)
    if not basename:
        return []

    search_dirs: list[str] = [parent]
    grandparent = os.path.dirname(parent)
    if grandparent and grandparent != parent:
        search_dirs.append(grandparent)

    scored_candidates: list[tuple[int, float, str]] = []
    seen: set[str] = set()

    for directory in search_dirs:
        # os.path answers False for a path longer than the platform allows; Path.is_dir raises on Python 3.13.
        if not os.path.isdir(directory):
            continue
        dir_path = Path(directory)
        try:
            entries = [entry.name for entry in dir_path.iterdir()]
        except OSError:
            continue

        target_base_lower = basename.lower()
        for entry_name in entries:
            candidate_path = os.path.join(directory, entry_name)
            if candidate_path in seen:
                continue

            entry_lower = entry_name.lower()
            # Bounded Levenshtein distance (max 2 edits)
            dist = levenshtein_distance_bounded(target_base_lower, entry_lower, max_dist=2)
            # The device check costs a realpath, so it runs only on the few names close enough to suggest.
            if dist <= 2 and not is_blocked_device_path(candidate_path):
                # Primary ranking: smallest distance, then SequenceMatcher ratio
                ratio = SequenceMatcher(None, target_base_lower, entry_lower).ratio()
                scored_candidates.append((dist, -ratio, candidate_path))
                seen.add(candidate_path)

        # Fallback if no Levenshtein-2 matches found
        if not scored_candidates:
            close_matches = get_close_matches(basename, entries, n=max_suggestions, cutoff=0.6)
            for match in close_matches:
                cand = os.path.join(directory, match)
                if cand not in seen and not is_blocked_device_path(cand):
                    seen.add(cand)
                    scored_candidates.append((3, 0.0, cand))

    scored_candidates.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in scored_candidates[:max_suggestions]]


def format_path_not_found_hint(target_path: str, suggestions: list[str]) -> str:
    """Format informative error message with suggested similar paths."""
    if not suggestions:
        return f"The path '{target_path}' does not exist. Please check the path and try again."
    joined = ", ".join(f"'{s}'" for s in suggestions)
    return f"The path '{target_path}' does not exist. Did you mean: {joined}?"


def mcp_namespace_error(target_path: str) -> str | None:
    """The error text for a search aimed at the virtual ``/mcp`` skill-doc namespace, or ``None`` for any other path.

    ``/mcp/<skill>/<function>.md`` is served by ``file_read_tool`` only; no directory exists for glob or grep to walk.
    Without this text the failure reads as a workspace-boundary error whose hints send the model on to bash, where
    ``/mcp`` is refused as well.
    """
    path = target_path.strip()
    if path != _MCP_NAMESPACE and not path.startswith(f"{_MCP_NAMESPACE}/"):
        return None
    return (
        f"'{target_path}' is the virtual MCP skill-doc namespace, not a directory, so glob_tool and grep_tool cannot "
        "search it. Read a function's documentation with file_read_tool on "
        "`/mcp/<skill_name>/<function_name>.md`; skill_select_tool lists every function name of a skill."
    )
