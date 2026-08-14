"""Pure builders for per-tool MCP config snippets shown in the Connect wizard.

[INPUT]
- ConnectionProfile (services.connect.service) — describes the target agent

[OUTPUT]
- build_config_json: returns the JSON/TOML MCP config for the external agent
- build_instructions: human-readable setup guidance shown in the wizard

[POS]
Kept free of I/O and state so the snippet layout can be unit-tested directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.connect.service import ConnectionProfile


def build_config_json(
    profile: "ConnectionProfile", mcp_url: str, token: str
) -> dict[str, object]:
    """Build the MCP config snippet for the external agent's config file.

    For TOML-based agents (Codex), returns a dict representation that
    the frontend displays as TOML. For JSON-based agents, returns the
    standard JSON config structure.
    """
    entry: dict[str, object] = {
        "myrm-memory": {
            "url": mcp_url,
            "transport": "streamable-http",
            "headers": {"Authorization": f"Bearer {token}"},
        }
    }
    if profile.config_format == "toml_mcp":
        toml_snippet = (
            f"[{profile.instructions_key}.myrm-memory]\n"
            f'url = "{mcp_url}"\n'
            f'transport = "streamable-http"\n\n'
            f"[{profile.instructions_key}.myrm-memory.headers]\n"
            f'Authorization = "Bearer {token}"\n'
        )
        return {"_format": "toml", "_toml_snippet": toml_snippet, profile.instructions_key: entry}
    return {profile.instructions_key: entry}


def build_instructions(profile: "ConnectionProfile", mcp_url: str) -> str:
    """Build human-readable setup instructions."""
    return (
        f"Add the following to your {profile.config_file_path}:\n"
        f"Under '{profile.instructions_key}', add a 'myrm-memory' entry "
        f"pointing to {mcp_url} with the generated Bearer token."
    )


__all__ = ["build_config_json", "build_instructions"]
