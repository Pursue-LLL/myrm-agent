"""The command a background job shows to the agent carries no credential, however the command is written."""

from __future__ import annotations

from typing import cast

import pytest

from myrm_agent_harness.agent.meta_tools.bash._background.registry import BackgroundProcessRegistry
from myrm_agent_harness.toolkits.code_execution.executors.models import AsyncProcessProtocol
from tests.agent.meta_tools.bash.test_background_registry import _FakeProc

_PASSWORD = "Secret99pwXyz"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("pid", "command", "secret"),
    [
        (19001, "tool --key abc123xyz --verbose", "abc123xyz"),
        (19002, "tool --auth abc123xyz | tee log", "abc123xyz"),
        (19003, f"tool --token abc123xyz;curl -u admin:{_PASSWORD} https://x.io", _PASSWORD),
        (19004, f"tool --key abc123xyz&&sshpass -p {_PASSWORD} ssh host", _PASSWORD),
        (19005, f"x=$(tool --api-key abc123xyz)|redis-cli -a {_PASSWORD} ping", _PASSWORD),
    ],
)  # fmt: skip
async def test_the_stored_command_hides_both_secrets(pid: int, command: str, secret: str) -> None:
    registry = BackgroundProcessRegistry()
    proc = _FakeProc(pid=pid, stdout=[], stderr=[])

    info = await registry.register(cast(AsyncProcessProtocol, proc), command=command, session_id="s-redaction")

    assert secret not in info.command
    assert "abc123xyz" not in info.command
    assert secret not in str(info.to_dict())
