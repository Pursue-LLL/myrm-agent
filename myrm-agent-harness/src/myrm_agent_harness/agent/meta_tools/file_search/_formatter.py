"""Grep result formatter.

[OUTPUT]
- compact_match_line: Truncates long match lines preserving match context
- format_grep_results: Formats search results into LLM-friendly output: files in path order, the result cap applied
  (a match beyond it only shows that the cap cut the search short), how many files were searched (when known), and
  whether a file cap or the time limit cut the scan short

[POS]
Grep output formatter. Transforms raw search matches into LLM-friendly output
with intelligent truncation, non-code file capping, and path-grouped
densification (eliminates repeated path strings when >= 5 matches).
"""

from __future__ import annotations

from pathlib import PurePosixPath

MAX_LINE_CHARS = 240
LINE_PREFIX_CONTEXT_CHARS = 80
NON_CODE_MATCH_CAP = 3
_DENSIFY_MIN_MATCHES = 5
_NON_CODE_EXTENSIONS = frozenset(
    {
        ".json",
        ".yaml",
        ".yml",
        ".md",
        ".txt",
        ".csv",
        ".toml",
        ".ini",
        ".cfg",
        ".xml",
        ".html",
        ".lock",
        ".log",
        ".svg",
    }
)


def compact_match_line(line: str, pattern: str, is_regex: bool) -> str:
    """Truncate long match lines, centering on the match point with surrounding context.

    If line length <= MAX_LINE_CHARS, returns unchanged.
    Otherwise, extracts a MAX_LINE_CHARS window around the first match occurrence
    and marks truncated regions.
    """
    char_count = len(line)
    if char_count <= MAX_LINE_CHARS:
        return line

    match_start = 0
    if not is_regex and pattern:
        idx = line.find(pattern)
        if idx >= 0:
            match_start = idx

    start = max(0, match_start - LINE_PREFIX_CONTEXT_CHARS)
    end = min(char_count, start + MAX_LINE_CHARS)
    start = max(0, end - MAX_LINE_CHARS)

    snippet = line[start:end]
    omitted_before = start
    omitted_after = char_count - end

    if omitted_before > 0 and omitted_after > 0:
        return f"\u2026{snippet} \u2026 [truncated: {omitted_before} before, {omitted_after} after]"
    if omitted_before > 0:
        return f"\u2026{snippet} [truncated: {omitted_before} before]"
    if omitted_after > 0:
        return f"{snippet} \u2026 [truncated: {omitted_after} after]"
    return snippet


def _is_non_code_file(file_path: str) -> bool:
    suffix = PurePosixPath(file_path).suffix.lower()
    return suffix in _NON_CODE_EXTENSIONS


def _within_cap(results: list[dict[str, str | int]], max_results: int) -> tuple[list[dict[str, str | int]], bool]:
    """The rows up to the ``max_results``-th match, and whether a match beyond it was found.

    The rows between the last match kept and the one beyond are context of either, so they go with it: the
    output ends at the last match kept.
    """
    kept = 0
    end = 0
    for index, row in enumerate(results):
        if row.get("type", "match") != "match":
            continue
        if kept == max_results:
            return results[:end], True
        kept += 1
        end = index + 1
    return results, False


def format_grep_results(
    results: list[dict[str, str | int]],
    pattern: str,
    files_searched: int | None,
    max_results: int,
    is_regex: bool = True,
    *,
    scan_limit: int | None = None,
    timed_out: bool = False,
) -> str:
    """Format grep results with non-code truncation and path-grouped densification.

    When total matches >= _DENSIFY_MIN_MATCHES, groups consecutive matches under
    a single path header to eliminate repeated path strings.
    Falls back to flat ``path:line: content`` format for small result sets where
    densification adds no benefit. Files are listed in path order, whatever order the search delivered them in.

    ``results`` may hold one match beyond ``max_results``: it only shows that the cap cut the search short, so it is
    not shown, and the output says the results were limited. A result with exactly ``max_results`` matches is
    complete and says nothing.

    ``files_searched`` is None when the caller cannot state the count (the ripgrep tier cannot), and the
    count is then left out. ``scan_limit`` is the file cap that cut the scan short, when one did, and ``timed_out``
    says that the time limit did.
    """
    notes: list[str] = []
    if scan_limit is not None:
        notes.append(
            f"... (scan limited to the first {scan_limit} files; narrow path or file_pattern to cover the rest)"
        )
    if timed_out:
        notes.append("... (search stopped at the time limit; narrow path or file_pattern to cover the rest)")
    searched = f" (searched {files_searched} file(s))" if files_searched is not None else ""

    if not results:
        footer = [f"No matches found for: {pattern}"]
        if files_searched is not None:
            footer.append(f"(Searched {files_searched} file(s))")
        return "\n".join([*footer, *notes])

    results, limited = _within_cap(results, max_results)

    matches_by_file: dict[str, list[dict[str, str | int]]] = {}
    for r in results:
        matches_by_file.setdefault(str(r["file"]), []).append(r)

    total_matches = sum(1 for r in results if r.get("type", "match") == "match")
    densify = total_matches >= _DENSIFY_MIN_MATCHES

    lines: list[str] = [f"Found {total_matches} match(es) for '{pattern}'{searched}:\n"]

    # Component-wise, the order glob_tool lists in: a directory's files stay together.
    for fp in sorted(matches_by_file, key=PurePosixPath):
        file_matches = matches_by_file[fp]

        is_non_code = _is_non_code_file(fp)
        visible_matches: list[dict[str, str | int]] = []
        match_count = 0

        for m in file_matches:
            if m.get("type", "match") == "match":
                match_count += 1
            if is_non_code and match_count > NON_CODE_MATCH_CAP:
                break
            visible_matches.append(m)

        total_file_matches = sum(1 for m in file_matches if m.get("type", "match") == "match")
        omitted_count = total_file_matches - match_count if is_non_code else 0

        if densify:
            lines.append(fp)

        last_line_num = -2
        for m in visible_matches:
            line_num = int(m["line"])
            content = compact_match_line(str(m["content"]), pattern, is_regex)
            line_type = m.get("type", "match")

            if last_line_num != -2 and line_num > last_line_num + 1:
                lines.append("  --" if densify else "--")
            last_line_num = line_num

            sep = ":" if line_type == "match" else "-"
            if densify:
                lines.append(f"  {line_num}{sep} {content}")
            else:
                lines.append(f"{fp}{sep}{line_num}{sep} {content}")

        if omitted_count > 0:
            lines.append(f"  ... {omitted_count} more non-code matches omitted in {fp}")

    if limited:
        lines.append(f"\n... (limited to first {max_results} results)")
    if notes:
        lines.append("\n" + "\n".join(notes))

    return "\n".join(lines)
