"""Tests for rg_matches — collecting ``rg --json`` events into grep rows.

Covers:
- Match and context events become rows; every other event is ignored
- The match cap stops the stream, and context rows do not count toward it
- A directory-level search withholds sensitive files before the cap counts them; a named file stays searchable
"""

from __future__ import annotations

import json

import pytest

from myrm_agent_harness.agent.meta_tools.file_search.rg_matches import RgMatches

SENSITIVE_PATHS = [
    "/w/.env",
    "/w/.aws/credentials",
    "/w/.ssh/id_ed25519",
    "/w/certs/server.pem",
    "/w/.docker/config.json",
]


def _event(kind: str, path: str, number: int, text: str) -> bytes:
    data = {"path": {"text": path}, "line_number": number, "lines": {"text": text + "\n"}}
    return json.dumps({"type": kind, "data": data}).encode() + b"\n"


class TestRows:
    def test_match_and_context_events_become_rows(self) -> None:
        matches = RgMatches(max_matches=10, withhold_sensitive=False)

        matches.feed(_event("context", "/w/a.py", 1, "before"))
        matches.feed(_event("match", "/w/a.py", 2, "needle"))

        assert matches.rows == [
            {"file": "/w/a.py", "line": 1, "content": "before", "type": "context"},
            {"file": "/w/a.py", "line": 2, "content": "needle", "type": "match"},
        ]

    def test_other_events_and_unreadable_lines_are_ignored(self) -> None:
        matches = RgMatches(max_matches=10, withhold_sensitive=False)
        binary_match = {
            "type": "match",
            "data": {"path": {"text": "/w/a.bin"}, "line_number": 1, "lines": {"bytes": "AAEC"}},
        }

        assert matches.feed(json.dumps({"type": "begin", "data": {"path": {"text": "/w/a.py"}}}).encode()) is False
        assert matches.feed(json.dumps({"type": "end", "data": {"path": {"text": "/w/a.py"}}}).encode()) is False
        assert matches.feed(json.dumps({"type": "summary", "data": {"stats": {"searches": 3}}}).encode()) is False
        assert matches.feed(b"not json\n") is False
        assert matches.feed(json.dumps(binary_match).encode()) is False
        assert matches.rows == []


class TestMatchCap:
    def test_stops_once_the_cap_of_matches_is_collected(self) -> None:
        matches = RgMatches(max_matches=2, withhold_sensitive=False)

        assert matches.feed(_event("match", "/w/a.py", 1, "needle")) is False
        assert matches.feed(_event("match", "/w/a.py", 2, "needle")) is True

    def test_context_rows_do_not_count_toward_the_cap(self) -> None:
        matches = RgMatches(max_matches=2, withhold_sensitive=False)

        for number in range(1, 6):
            assert matches.feed(_event("context", "/w/a.py", number, "around")) is False
        assert matches.feed(_event("match", "/w/a.py", 6, "needle")) is False


class TestSensitiveFiles:
    @pytest.mark.parametrize("path", SENSITIVE_PATHS)
    def test_directory_search_withholds_them(self, path: str) -> None:
        matches = RgMatches(max_matches=10, withhold_sensitive=True)

        assert matches.feed(_event("match", path, 1, "needle")) is False
        assert matches.feed(_event("context", path, 2, "around")) is False

        assert matches.rows == []

    @pytest.mark.parametrize("path", SENSITIVE_PATHS)
    def test_a_named_file_stays_searchable(self, path: str) -> None:
        matches = RgMatches(max_matches=10, withhold_sensitive=False)

        matches.feed(_event("match", path, 1, "needle"))

        assert [row["file"] for row in matches.rows] == [path]

    def test_ordinary_hidden_files_are_not_withheld(self) -> None:
        matches = RgMatches(max_matches=10, withhold_sensitive=True)

        matches.feed(_event("match", "/w/.github/workflows/ci.yml", 1, "needle"))

        assert [row["file"] for row in matches.rows] == ["/w/.github/workflows/ci.yml"]

    def test_withheld_matches_do_not_count_toward_the_cap(self) -> None:
        matches = RgMatches(max_matches=2, withhold_sensitive=True)

        for number in range(1, 6):
            assert matches.feed(_event("match", "/w/.env", number, "needle")) is False
        assert matches.feed(_event("match", "/w/a.py", 1, "needle")) is False
        assert matches.feed(_event("match", "/w/b.py", 1, "needle")) is True

        assert [row["file"] for row in matches.rows] == ["/w/a.py", "/w/b.py"]
