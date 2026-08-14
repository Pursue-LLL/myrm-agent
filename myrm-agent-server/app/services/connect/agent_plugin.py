"""Agent Plugins 1.0.0 portable bundle generation for external agent memory access.

[INPUT]
- app.core.infra.ingress / settings — resolved by ConnectService before building

[OUTPUT]
- build_agent_plugin_bundle: renders plugin.json / mcp.json / SKILL.md into a
  standards-compliant Agent Plugins 1.0.0 bundle (transport-only).

[POS]
The Agent Plugins standard (agent-plugins.org) lets one portable bundle
distribute an MCP server to every client that supports it (VS Code, Copilot,
Kiro, Cursor, ChatGPT, Codex, ...). Myrm already exposes a Streamable HTTP
/mcp endpoint; this module turns it into a standards-compliant bundle so any
agent client can attach Myrm's long-term memory.

Token modes:
- env (default): mcp.json references $MYRM_MCP_TOKEN so the bundle stays
  credential-free and safe to commit. Most clients substitute ${VAR}; some
  (VS Code, Cursor) use ${env:VAR}.
- embedded: the token is inlined into mcp.json for clients that cannot
  interpolate — an explicit, revocable choice.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

# Connector state id used for the Agent Plugins token. It is intentionally not a
# member of PROFILES (per-tool config snippets) because a bundle is client-agnostic.
AGENT_PLUGIN_PROFILE = "agent_plugin"

# Env var name referenced by mcp.json in non-embedded token mode.
TOKEN_ENV_VAR = "MYRM_MCP_TOKEN"

_PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
_MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"


@dataclass(frozen=True)
class AgentPluginBundle:
    """A standards-compliant Agent Plugins 1.0.0 memory bundle."""

    agent_id: str
    mcp_url: str
    token: str
    embed_token: bool
    files: dict[str, str]
    instructions: str


def _build_plugin_json() -> str:
    """Render plugin.json (manifest)."""
    manifest = {
        "$schema": _PLUGIN_SCHEMA,
        "name": "myrm-memory",
        "version": "1.0.0",
        "description": (
            "Persistent long-term memory for AI agents. Recall relevant past "
            "context before answering and store durable facts as you work, backed "
            "by Myrm's memory engine."
        ),
        "author": {"name": "Myrm", "url": "https://myrmagent.ai"},
        "homepage": "https://myrmagent.ai",
        "license": "MIT",
        "keywords": ["memory", "long-term-memory", "recall", "store", "mcp", "agent-memory"],
        "extensions": {
            "ai.myrm.memory": {
                "agentScope": (
                    "This bundle's token is bound to one Myrm agent profile. "
                    "Regenerate a token in Myrm's connect wizard to switch scope; "
                    "revoke to disconnect immediately."
                ),
                "selfHosted": (
                    "Point the mcp.json URL at your own Myrm instance (local, "
                    "desktop, or cloud) instead of the generated one. The plugin "
                    "is transport-only and works against any compatible endpoint."
                ),
            }
        },
    }
    return json.dumps(manifest, indent=2)


def _build_mcp_json(url: str, token: str, embed_token: bool) -> str:
    """Render mcp.json with the token either env-referenced (default) or inlined."""
    authorization = f"Bearer {token}" if embed_token else f"Bearer ${{{TOKEN_ENV_VAR}}}"
    config = {
        "$schema": _MCP_SCHEMA,
        "mcpServers": {
            "myrm-memory": {
                "type": "streamable-http",
                "url": url,
                "headers": {"Authorization": authorization},
            }
        },
    }
    return json.dumps(config, indent=2)


#: SKILL.md handed to the consuming agent. Written for best-model comprehension
#: with low-token redundancy; every capability mentioned matches the real MCP
#: tool signatures (see memory/agent_surface/mcp_server.py).
_SKILL_MARKDOWN = """---
name: myrm-memory
description: Persistent long-term memory that survives across sessions. Use it to recall what the user previously said, did, or preferred before answering; to store durable facts, preferences, and rules as you learn them; and to correct outdated memories. Relevant whenever continuity matters — the user refers to earlier work, states a lasting preference, or asks a question that accumulated context could answer.
---

# Persistent long-term memory

This plugin gives you a long-term memory that persists across sessions and is shared with the user's other assistants. Memories are short, standalone, durable facts: preferences, project knowledge, standing rules, and decisions.

The server exposes four tools — `memory_recall`, `memory_store`, `memory_list`, `memory_manage`.

## Recall before you answer

Call `memory_recall` whenever the user refers to earlier work, a past decision, or anything already discussed; states a preference or constraint that may already be recorded; or asks a question prior context could answer.

```json
{"name": "memory_recall", "arguments": {"query": "How does the user prefer to deploy, and where?"}}
```

Ground your answer in what is returned. If nothing relevant comes back, say so plainly — never invent continuity.

## Store durable facts

Call `memory_store` when you learn something durable and reusable:

- Stable user preferences → `category: "preference"`, with a short `preference_key` such as `"package_manager"`.
- Project facts and decisions → `category: "knowledge"`.
- Standing rules the user wants followed → `category: "rule"`, with a `rule_trigger` describing when the rule applies.

```json
{"name": "memory_store", "arguments": {"content": "User deploys the API to us-east-1 via GitHub Actions on push to main.", "category": "knowledge"}}
```

Keep each entry to one standalone fact. Store the fact, not the transcript. Use `write_target: "shared"` only when a fact applies to the user across all of their assistants; the default `"bound"` scope keeps it with this agent. Never store passwords, API keys, or other secrets — memory is shared across all of the user's assistants, so a secret stored once is exposed everywhere.

## Audit before you duplicate

Call `memory_list` to browse what is already stored before saving a near-duplicate. When a recalled fact is outdated, call `memory_manage` with `action: "correct"` (knowledge) or `"update"` plus the memory id, instead of storing a conflicting copy.

## Trust the user

Memory is an aid, not ground truth. If a stored fact conflicts with what the user tells you now, the user wins — correct the memory and move on.
"""


def build_agent_plugin_bundle(
    mcp_url: str,
    token: str,
    *,
    agent_id: str,
    embed_token: bool = False,
) -> AgentPluginBundle:
    """Render the full Agent Plugins 1.0.0 bundle for a Myrm memory endpoint.

    The default (env) mode keeps mcp.json free of credentials, per the Agent
    Plugins spec (headers are visible package data, not a secret mechanism).
    Most clients substitute ``${VAR}``; some (VS Code, Cursor) use ``${env:VAR}``.
    Embedded mode is offered for clients that cannot interpolate and inlines the
    token directly — it is the user's explicit choice and revocable at any time.
    """
    files = {
        "plugin.json": _build_plugin_json(),
        "mcp.json": _build_mcp_json(mcp_url, token, embed_token),
        "skills/myrm-memory/SKILL.md": _SKILL_MARKDOWN,
    }
    if embed_token:
        instructions = (
            f"Place this bundle in your agent client's plugin directory and enable it. "
            f"The token is inlined into mcp.json, so keep the bundle out of version "
            f"control. It is bound to the Myrm agent '{agent_id}'; regenerate it in "
            f"Myrm's connect wizard to switch scope, or revoke to disconnect immediately."
        )
    else:
        env_ref = f"${{{TOKEN_ENV_VAR}}}"
        env_ref_vscode = f"${{env:{TOKEN_ENV_VAR}}}"
        instructions = (
            f"Place this bundle in your agent client's plugin directory and export "
            f"{TOKEN_ENV_VAR} (below) in your shell profile. mcp.json reads the token "
            f"from the environment, so the bundle is safe to commit to version control. "
            f"Most clients substitute {env_ref}; if yours uses {env_ref_vscode} (VS Code, "
            f"Cursor) or does not interpolate, adjust the Authorization value in mcp.json."
        )
    return AgentPluginBundle(
        agent_id=agent_id,
        mcp_url=mcp_url,
        token=token,
        embed_token=embed_token,
        files=files,
        instructions=instructions,
    )


__all__ = [
    "AGENT_PLUGIN_PROFILE",
    "TOKEN_ENV_VAR",
    "AgentPluginBundle",
    "build_agent_plugin_bundle",
]
