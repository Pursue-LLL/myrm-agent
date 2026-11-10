"""Preference radar: the server schemas and the frontend service declare the same flat fields.

The tune request refuses fields it does not know and the state response is read field by field, so a field one side
renames breaks the radar drawer: the change is refused, or the weights read as undefined and the drawer shows the wrong
ones.
"""

from __future__ import annotations

import re

import pytest

from app.schemas.memory.radar import PreferenceRadarStateResponse, UpdatePreferenceRadarRequest
from tests.support.frontend_api_paths import FRONTEND_SRC

_PREFERENCES = FRONTEND_SRC / "services" / "memory" / "preferences.ts"
_DIMENSIONS_RE = re.compile(r"export interface RadarDimensionValues \{(?P<body>.*?)\n\}", re.DOTALL)
_STATE_RE = re.compile(
    r"export interface PreferenceRadarStateResponse extends RadarDimensionValues \{(?P<body>.*?)\n\}", re.DOTALL
)
_TUNE_RE = re.compile(r"export type PreferenceRadarTuneRequest = Partial<RadarDimensionValues> & \{(?P<body>.*?)\n\};", re.DOTALL)
_PROPERTY_RE = re.compile(r"^\s*(?P<name>\w+)\??:", re.MULTILINE)


def _fields(declaration: re.Pattern[str]) -> set[str]:
    match = declaration.search(_PREFERENCES.read_text(encoding="utf-8"))
    assert match, f"{declaration.pattern} not found in {_PREFERENCES}"
    return set(_PROPERTY_RE.findall(match.group("body")))


def _assert_same(server: set[str], frontend: set[str], what: str) -> None:
    assert len(frontend) > 5, f"frontend {what} scan found almost no fields; the scan is broken"
    assert not server - frontend, f"The server {what} has fields preferences.ts does not declare: {sorted(server - frontend)}"
    assert not frontend - server, f"preferences.ts {what} declares fields the server does not have: {sorted(frontend - server)}"


@pytest.mark.skipif(not _PREFERENCES.is_file(), reason="frontend sources are not part of this checkout")
def test_state_fields_match_between_server_and_frontend() -> None:
    _assert_same(
        set(PreferenceRadarStateResponse.model_fields),
        _fields(_DIMENSIONS_RE) | _fields(_STATE_RE),
        "radar state response",
    )


@pytest.mark.skipif(not _PREFERENCES.is_file(), reason="frontend sources are not part of this checkout")
def test_tune_request_fields_match_between_server_and_frontend() -> None:
    _assert_same(
        set(UpdatePreferenceRadarRequest.model_fields),
        _fields(_DIMENSIONS_RE) | _fields(_TUNE_RE),
        "radar tune request",
    )
