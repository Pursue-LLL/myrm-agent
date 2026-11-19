"""Unified Runs Hub enums: the values the API can send and the values the web client's types allow must agree,
and the Hub's cron and failed statuses must agree with the cron toolkit that stores them.

[POS]
tests/architecture/test_run_status_parity.py

[INPUT]
- app/api/runs/schemas.py: the `RunSource`, `RunStatus` and `RunStopReasonCategory` literals, `CRON_RUN_STATUSES`
  and `FAILED_RUN_STATUSES`
- myrm-agent-frontend services/runs.ts: the union types of the same names
- myrm_agent_harness.toolkits.cron: `RunStatus` (the statuses a cron run is stored with) and `matching_run_statuses`
  (the stored statuses a failed filter selects)

[OUTPUT]
- Fails when the API can send a value the web client has no member for (the Hub row renders without that state's
  icon or label)
- Fails when the web client lists a value the API never sends (a dead union member)
- Fails when the cron toolkit stores a status the Hub does not map, or counts a failure the Failed filter hides
"""

from __future__ import annotations

import re
from typing import get_args

import pytest
from myrm_agent_harness.toolkits.cron import RunStatus as CronRunStatus
from myrm_agent_harness.toolkits.cron import matching_run_statuses

from app.api.runs.schemas import (
    CRON_RUN_STATUSES,
    FAILED_RUN_STATUSES,
    RunSource,
    RunStatus,
    RunStopReasonCategory,
)
from tests.support.frontend_api_paths import FRONTEND_SRC

_FRONTEND_RUNS = FRONTEND_SRC / "services" / "runs.ts"

_API_ENUMS: dict[str, object] = {
    "RunSource": RunSource,
    "RunStatus": RunStatus,
    "RunStopReasonCategory": RunStopReasonCategory,
}
_QUOTED_RE = re.compile(r"'([a-z_]+)'")


def _frontend_members(name: str) -> set[str]:
    match = re.search(rf"export type {name}\s*=\s*(?P<body>[^;]+);", _FRONTEND_RUNS.read_text(encoding="utf-8"))
    assert match, f"`export type {name}` not found in {_FRONTEND_RUNS}"
    return set(_QUOTED_RE.findall(match.group("body")))


@pytest.mark.skipif(not _FRONTEND_RUNS.is_file(), reason="frontend sources are not part of this checkout")
@pytest.mark.parametrize("name", sorted(_API_ENUMS))
def test_run_enum_matches_between_api_and_web_client(name: str) -> None:
    api = set(get_args(_API_ENUMS[name]))
    frontend = _frontend_members(name)

    assert not api - frontend, (
        f"The API can send {name} values the web client has no member for (add them to services/runs.ts and give "
        f"the Hub row an icon and label): {sorted(api - frontend)}"
    )
    assert not frontend - api, f"services/runs.ts lists {name} values the API never sends (remove them): {sorted(frontend - api)}"


def test_hub_maps_exactly_the_statuses_the_cron_toolkit_stores() -> None:
    assert {status.value for status in CronRunStatus} == CRON_RUN_STATUSES


def test_the_failed_filter_hides_no_failure_the_cron_store_reports() -> None:
    assert matching_run_statuses("error") <= FAILED_RUN_STATUSES
