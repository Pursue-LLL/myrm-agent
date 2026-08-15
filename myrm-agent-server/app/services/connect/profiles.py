"""External agent connection profiles.

[INPUT]
- #doc conventions — frozen dataclass + typed literal fields

[OUTPUT]
- ConnectionProfile: describes how a specific external agent connects to the MCP server
- PROFILES: registry of supported external agents and their config file details

[POS]
Static data layer for the Connect Wizard: the authoritative list of supported
external agents (Claude Code, Cursor, Windsurf, Codex, Gemini CLI) and where
their on-disk MCP configs live. Kept separate from ConnectService so the
profile registry stays a pure, dependency-free definition.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ConnectionProfile:
    """Describes how a specific external agent connects to our MCP server."""

    id: str
    label: str
    description: str
    config_format: Literal["json_mcp", "toml_mcp"]
    config_file_path: str
    instructions_key: str


# Supported external agents and their MCP config details
PROFILES: dict[str, ConnectionProfile] = {
    "claude_code": ConnectionProfile(
        id="claude_code",
        label="Claude Code",
        description="Anthropic's Claude Code CLI agent",
        config_format="json_mcp",
        config_file_path="~/.claude.json",
        instructions_key="mcpServers",
    ),
    "cursor": ConnectionProfile(
        id="cursor",
        label="Cursor",
        description="Cursor IDE AI assistant",
        config_format="json_mcp",
        config_file_path="~/.cursor/mcp.json",
        instructions_key="mcpServers",
    ),
    "windsurf": ConnectionProfile(
        id="windsurf",
        label="Windsurf",
        description="Codeium Windsurf IDE agent",
        config_format="json_mcp",
        config_file_path="~/.codeium/windsurf/mcp_config.json",
        instructions_key="mcpServers",
    ),
    "codex": ConnectionProfile(
        id="codex",
        label="Codex CLI",
        description="OpenAI Codex CLI agent",
        config_format="toml_mcp",
        config_file_path="~/.codex/config.toml",
        instructions_key="mcp_servers",
    ),
    "gemini_cli": ConnectionProfile(
        id="gemini_cli",
        label="Gemini CLI",
        description="Google Gemini CLI agent",
        config_format="json_mcp",
        config_file_path="~/.gemini/settings.json",
        instructions_key="mcpServers",
    ),
}


__all__ = ["PROFILES", "ConnectionProfile"]
