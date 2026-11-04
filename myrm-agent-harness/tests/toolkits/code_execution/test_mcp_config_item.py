"""MCPConfigItem carries the one setting the host needs to size a script's time: the server's tool-call limit."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.code_execution import MCPConfigItem
from myrm_agent_harness.toolkits.mcp.config import MCPConfig


def _item(**overrides: object) -> MCPConfigItem:
    return MCPConfigItem.from_dict({"name": "srv", "type": "stdio", "command": "echo", **overrides})


def test_the_configured_execute_timeout_is_read() -> None:
    assert _item(execute_timeout=300).execute_timeout == 300.0
    assert _item(execute_timeout=12.5).execute_timeout == 12.5


def test_the_default_is_the_one_the_server_config_applies() -> None:
    """A skill config written without the key must be sized by the limit the connection will actually use."""
    server_default = MCPConfig(name="srv", type="stdio", command="echo", description="d").execute_timeout

    assert _item().execute_timeout == server_default == MCPConfigItem(name="srv").execute_timeout


@pytest.mark.parametrize("unusable", [None, "soon", 0, -5, [], True])
def test_an_unusable_value_falls_back_to_the_default(unusable: object) -> None:
    assert _item(execute_timeout=unusable).execute_timeout == MCPConfigItem(name="srv").execute_timeout


def test_a_list_of_dicts_keeps_each_servers_own_limit() -> None:
    items = MCPConfigItem.from_dict_list([{"name": "a", "execute_timeout": 30}, {"name": "b", "execute_timeout": 400}])

    assert [item.execute_timeout for item in items] == [30.0, 400.0]
