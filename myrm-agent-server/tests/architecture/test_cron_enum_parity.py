"""Cron value sets: the values a job and its runs carry must agree with the members of the web client's types.

[POS]
tests/architecture/test_cron_enum_parity.py

[INPUT]
- myrm_agent_harness.toolkits.cron: `JobStatus`, `RunStatus`, `PauseReason`, `SessionTarget` and `JobType`
- myrm_agent_harness.infra.incremental: `MonitorType`
- myrm-agent-frontend services/cron.types.ts: the union types of the same names

[OUTPUT]
- Fails when the cron toolkit can send a value the web client has no member for (a page keyed on the type cannot name
  that state)
- Fails when the web client lists a value the cron toolkit never sends (a dead union member)
"""

from __future__ import annotations

import re
from typing import get_args

import pytest
from myrm_agent_harness.infra.incremental import MonitorType
from myrm_agent_harness.toolkits.cron import JobStatus, JobType, PauseReason, RunStatus, SessionTarget

from tests.support.frontend_api_paths import FRONTEND_SRC

_FRONTEND_CRON_TYPES = FRONTEND_SRC / "services" / "cron.types.ts"

_TOOLKIT_VALUES: dict[str, frozenset[str]] = {
    "JobStatus": frozenset(member.value for member in JobStatus),
    "RunStatus": frozenset(member.value for member in RunStatus),
    "PauseReason": frozenset(member.value for member in PauseReason),
    "SessionTarget": frozenset(member.value for member in SessionTarget),
    "JobType": frozenset(member.value for member in JobType),
    "MonitorType": frozenset(get_args(MonitorType)),
}
_QUOTED_RE = re.compile(r"'([a-z_]+)'")


def _frontend_members(name: str) -> set[str]:
    match = re.search(rf"export type {name}\s*=\s*(?P<body>[^;]+);", _FRONTEND_CRON_TYPES.read_text(encoding="utf-8"))
    assert match, f"`export type {name}` not found in {_FRONTEND_CRON_TYPES}"
    return set(_QUOTED_RE.findall(match.group("body")))


@pytest.mark.skipif(not _FRONTEND_CRON_TYPES.is_file(), reason="frontend sources are not part of this checkout")
@pytest.mark.parametrize("name", sorted(_TOOLKIT_VALUES))
def test_cron_value_set_matches_the_web_client_type(name: str) -> None:
    toolkit = _TOOLKIT_VALUES[name]
    frontend = _frontend_members(name)

    assert not toolkit - frontend, (
        f"The cron toolkit can send {name} values the web client has no member for (add them to services/cron.types.ts "
        f"and to everything keyed on the type): {sorted(toolkit - frontend)}"
    )
    assert not frontend - toolkit, (
        f"services/cron.types.ts lists {name} values the cron toolkit never sends (remove them): {sorted(frontend - toolkit)}"
    )
