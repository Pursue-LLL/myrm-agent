"""MCP server entries and IPC settings that a code-execution run is given.

[INPUT]
- (none)

[OUTPUT]
- MCPConfigItem: One MCP server a script run can call, including the limit its tool calls are held to.
- MCPCommunicationConfig: MCP IPC communication config provided by CodeExecutor.

[POS]
Plain data describing the MCP servers visible to one execution. Kept apart from ``models`` so the host can size a
script's time from the servers' own limits without that module growing past its size budget.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Mirrors ``MCPConfig.execute_timeout``: a skill config written without the key is sized by the limit its connection
# will actually enforce. ``test_mcp_config_item`` pins the two together.
_DEFAULT_EXECUTE_TIMEOUT_SECONDS = 120.0


@dataclass
class MCPConfigItem:
    """MCP tool configuration item."""

    name: str
    type: str = "stdio"
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None
    description: str = ""
    execute_timeout: float = _DEFAULT_EXECUTE_TIMEOUT_SECONDS

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> MCPConfigItem:
        """Create MCPConfigItem from a dictionary."""
        args_raw = data.get("args")
        args_list: list[str] | None = None
        if args_raw and isinstance(args_raw, list):
            args_list = [str(arg) for arg in args_raw]

        env_raw = data.get("env")
        env_dict: dict[str, str] | None = None
        if env_raw and isinstance(env_raw, dict):
            env_dict = {str(key): str(value) for key, value in env_raw.items()}

        execute_timeout = _DEFAULT_EXECUTE_TIMEOUT_SECONDS
        timeout_raw = data.get("execute_timeout")
        if isinstance(timeout_raw, int | float) and not isinstance(timeout_raw, bool) and timeout_raw > 0:
            execute_timeout = float(timeout_raw)

        return cls(
            name=str(data.get("name", "")),
            type=str(data.get("type", "stdio")),
            command=str(data.get("command")) if data.get("command") else None,
            args=args_list,
            env=env_dict,
            url=str(data.get("url")) if data.get("url") else None,
            description=str(data.get("description", "")),
            execute_timeout=execute_timeout,
        )

    @classmethod
    def from_dict_list(cls, data_list: list[dict[str, object]]) -> list[MCPConfigItem]:
        """Create a list of MCPConfigItem from dictionaries."""
        return [cls.from_dict(data) for data in data_list]


@dataclass
class MCPCommunicationConfig:
    """MCP IPC communication config provided by CodeExecutor."""

    socket_path: str | None = None
    skip_local_proxy: bool = False
    servers: list[MCPConfigItem] = field(default_factory=list)
