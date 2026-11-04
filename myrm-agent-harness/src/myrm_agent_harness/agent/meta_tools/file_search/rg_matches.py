"""Grep rows collected from a ripgrep ``--json`` stream.

[INPUT]
- core.security.path::is_sensitive_file (POS: single source of truth for the sensitive file patterns)

[OUTPUT]
- RgMatches: grep rows of one ripgrep run, fed line by line

[POS]
Turns ripgrep's event stream into the rows ``grep_tool`` formats. A search over a directory never returns the
lines of a sensitive file (``.env``, private keys, credentials): reading such a file by name goes through an
approval, and a search that walks into its directory would hand the same lines to the model without one.
The stream's summary event is not read: before ripgrep 15 its file count covers only the files that printed
output, so it cannot say how many files were searched.
"""

from __future__ import annotations

import json

from myrm_agent_harness.core.security.path import is_sensitive_file


class RgMatches:
    """Rows of one ripgrep run; call :meth:`feed` with every stdout line."""

    def __init__(self, max_matches: int, *, withhold_sensitive: bool) -> None:
        self.rows: list[dict[str, str | int]] = []
        self._max_matches = max_matches
        self._withhold_sensitive = withhold_sensitive
        self._match_count = 0
        self._withheld: dict[str, bool] = {}

    def feed(self, line: bytes) -> bool:
        """Take one stdout line; True once ``max_matches`` matches are collected and ripgrep may stop."""
        try:
            event = json.loads(line)
            kind = event["type"]
            if kind not in ("match", "context"):
                return False
            data = event["data"]
            path = data["path"]["text"]
            row: dict[str, str | int] = {
                "file": path,
                "line": data["line_number"],
                "content": data["lines"]["text"].rstrip("\n"),
                "type": kind,
            }
        except (ValueError, KeyError, TypeError):
            return False
        if self._is_withheld(path):
            return False
        self.rows.append(row)
        if kind == "context":
            return False
        self._match_count += 1
        return self._match_count >= self._max_matches

    def _is_withheld(self, path: str) -> bool:
        if not self._withhold_sensitive:
            return False
        withheld = self._withheld.get(path)
        if withheld is None:
            withheld = self._withheld[path] = is_sensitive_file(path)
        return withheld
