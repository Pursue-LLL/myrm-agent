"""Loop guard pause: the clients that tell it from an approval must look for the marker the harness sends.

[POS]
tests/architecture/test_tool_stuck_pause_clients.py

[INPUT]
- myrm_agent_harness agent.errors: `TOOL_STUCK_ACTION_TYPE`
- myrm-agent-frontend toolsProgressEvents.ts and myrm-agent-extension approval.js: their `action_type` comparisons

[OUTPUT]
- Fails when a client no longer compares `action_type` with the harness marker (the pause would open an approval card
  there, and the extension would lock its input)
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from myrm_agent_harness.agent.errors import TOOL_STUCK_ACTION_TYPE

_ROOT = Path(__file__).resolve().parents[3]
_CLIENTS = {
    "web app": _ROOT / "myrm-agent-frontend/src/store/chat/messageStream/handlers/toolsProgressEvents.ts",
    "extension side panel": _ROOT / "myrm-agent-extension/src/sidepanel/approval.js",
}
_ACTION_TYPE_COMPARISON = re.compile(r"""action_type\s*===\s*['"]([\w-]+)['"]""")


@pytest.mark.parametrize("client", _CLIENTS)
def test_client_looks_for_the_marker_the_harness_sends(client: str) -> None:
    source = _CLIENTS[client]
    if not source.is_file():
        pytest.skip(f"{client} sources are not part of this checkout")

    compared = _ACTION_TYPE_COMPARISON.findall(source.read_text(encoding="utf-8"))

    assert TOOL_STUCK_ACTION_TYPE in compared, (
        f"{client}: {source.name} compares action_type with {compared}, not with the loop guard marker "
        f"{TOOL_STUCK_ACTION_TYPE!r}; it would show the pause as an approval to answer"
    )
