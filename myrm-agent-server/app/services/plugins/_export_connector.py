"""Portable connector declarations for expert export (business layer).

A shared connector is a declaration the receiver completes with their own secrets:
credentials are never copied, only the names of the secrets the connector needs.
Anything that would only work on this machine (local launch paths, files bundled by
another package) or that carries credential material inside the declaration is not
shared; the caller lists it as "not included" instead.

[INPUT]
- myrm_agent_harness.agent.plugins.integrity::verify_mcp_server_artifacts (POS: local entrypoint detection.)
- myrm_agent_harness.agent.skills.security.content_sanitizer::content_sanitizer (POS: secret detection.)
- ._mcp_persist::SECRET_REF_PATTERN, is_secret_reference (POS: ``{{secret:KEY}}`` reference grammar.)

[OUTPUT]
- ConnectorOutcome: the portable declaration, or the reason it cannot be shared.
- connector_from_config: stored ``mcpServers`` entry -> portable declaration.
- secret_names_of: names of the secrets a shared connector asks the recipient to provide.

[POS]
Pure inverse of the import-side connector persistence. No I/O.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

from myrm_agent_harness.agent.plugins.integrity import verify_mcp_server_artifacts
from myrm_agent_harness.agent.plugins.models import PluginMcpServer
from myrm_agent_harness.agent.skills.security.content_sanitizer import content_sanitizer

from ._export_models import Omit
from ._mcp_persist import SECRET_REF_PATTERN, is_secret_reference

__all__ = ["ConnectorOutcome", "connector_from_config", "secret_names_of"]

_TRANSPORTS = {
    "stdio": "stdio",
    "sse": "sse",
    "streamable_http": "streamable_http",
    "streamable-http": "streamable_http",
    "http": "streamable_http",
}
# Absolute, home-relative, relative-to-cwd, Windows drive and UNC paths only exist on this machine.
_LOCAL_PATH = re.compile(r"^(?:/|~|\.{1,2}/|[A-Za-z]:[\\/]|\\\\)")
_MAX_SECRET_NAME_CHARS = 128


@dataclass(frozen=True)
class ConnectorOutcome:
    server: PluginMcpServer | None = None
    omit: Omit | None = None


def connector_from_config(cfg: Mapping[str, object]) -> ConnectorOutcome:
    """Project a stored connector onto a portable declaration (secret names only)."""
    name = _text(cfg.get("name"))
    extra = cfg.get("extra_params")
    extra_params: Mapping[str, object] = extra if isinstance(extra, dict) else {}
    if extra_params.get("plugin_root") or extra_params.get("data_root"):
        return ConnectorOutcome(omit=Omit.CONNECTOR_BUNDLED_FILES)

    command, url, cwd = _text(cfg.get("command")), _text(cfg.get("url")), _text(extra_params.get("cwd"))
    args = _strings(cfg.get("args"))
    transport = _transport(cfg.get("type"), command, url)
    if not name or transport is None:
        return ConnectorOutcome(omit=Omit.CONNECTOR_UNSUPPORTED)

    if transport == "stdio":
        if not command:
            return ConnectorOutcome(omit=Omit.CONNECTOR_UNSUPPORTED)
        if any(_is_local_path(value) for value in (command, cwd, *args)):
            return ConnectorOutcome(omit=Omit.CONNECTOR_LOCAL_PATH)
    elif not url.lower().startswith(("http://", "https://")):
        return ConnectorOutcome(omit=Omit.CONNECTOR_UNSUPPORTED)
    elif _has_credentials_in_url(url):
        return ConnectorOutcome(omit=Omit.CONNECTOR_SECRET_MATERIAL)

    shared_parts = (command, *args, cwd) if transport == "stdio" else (url,)
    declaration = "\n".join(part for part in shared_parts if part)
    if declaration and not content_sanitizer.sanitize(declaration, "connector.txt").is_safe:
        return ConnectorOutcome(omit=Omit.CONNECTOR_SECRET_MATERIAL)

    if transport == "stdio":
        env_keys = _secret_names(cfg, extra_params)
        server = PluginMcpServer(
            name=name,
            server_type=transport,
            command=command,
            args=args or None,
            url=None,
            headers=None,
            cwd=cwd or None,
            env_key_names=env_keys,
            raw_env=dict.fromkeys(env_keys, ""),
        )
        if not verify_mcp_server_artifacts(server, ())[0]:
            return ConnectorOutcome(omit=Omit.CONNECTOR_LOCAL_PATH)
        return ConnectorOutcome(server=server)

    # A remote connector is just its URL plus header placeholders; the format has no place for the rest.
    remote = PluginMcpServer(
        name=name,
        server_type=transport,
        command=None,
        args=None,
        url=url,
        headers=_portable_headers(cfg.get("headers")),
        cwd=None,
    )
    return ConnectorOutcome(server=remote)


def secret_names_of(server: PluginMcpServer) -> list[str]:
    """Secrets the recipient must provide: environment variable names plus header placeholder keys."""
    header_keys = [key for value in (server.headers or {}).values() for key in SECRET_REF_PATTERN.findall(value)]
    return sorted({*server.env_key_names, *header_keys})


def _transport(raw: object, command: str, url: str) -> str | None:
    declared = _text(raw).lower()
    if declared:
        return _TRANSPORTS.get(declared)
    if command:
        return "stdio"
    if url:
        return "streamable_http" if "/mcp" in url else "sse"
    return None


def _is_local_path(value: str) -> bool:
    # ``--flag=/path`` keeps its path on the right of the first "="
    candidate = value.split("=", 1)[1] if value.startswith("-") and "=" in value else value
    return bool(_LOCAL_PATH.match(candidate.strip()))


def _has_credentials_in_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return True
    return bool(parts.username or parts.password)


def _portable_headers(raw: object) -> dict[str, str] | None:
    """Keep ``{{secret:KEY}}`` references; any literal value becomes a placeholder keyed by the header name."""
    if not isinstance(raw, dict):
        return None
    headers = {
        str(key): value if isinstance(value, str) and is_secret_reference(value) else "{{secret:" + str(key) + "}}"
        for key, value in raw.items()
        if str(key).strip()
    }
    return headers or None


def _secret_names(cfg: Mapping[str, object], extra_params: Mapping[str, object]) -> list[str]:
    """Names of the secrets the connector needs (declared secrets plus environment variable names)."""
    names = _strings(cfg.get("required_secrets"))
    env = extra_params.get("env")
    if isinstance(env, dict):
        names.extend(str(key).strip() for key in env if str(key).strip())
    return list(dict.fromkeys(name[:_MAX_SECRET_NAME_CHARS] for name in names))


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _strings(value: object) -> list[str]:
    return [item.strip() for item in value if isinstance(item, str) and item.strip()] if isinstance(value, list) else []
