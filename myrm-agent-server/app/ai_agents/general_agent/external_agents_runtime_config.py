"""External-agent runtime config normalization and fingerprint helpers.

[INPUT]
- myrm_agent_harness.toolkits.acp.backend_detector::BackendDetector (POS: CLI backend detection)
- myrm_agent_harness.toolkits.acp.types::RuntimeConfig (POS: ACP runtime config contract)
- app.config.deploy_mode::is_local_mode (POS: deploy mode guard)

[OUTPUT]
- _default_cli_args: Known CLI defaults for local auto-detect
- _auth_mode / _cfg_int: Config parsing helpers
- _config_fingerprint: Stable hash aligned with RuntimeConfig-relevant fields
- _resolve_external_agent_cfgs: Resolve explicit config or local auto-detect
- _register_backends_on_pool: Register normalized runtime configs into RuntimePool

[POS]
GeneralAgent 外部 Agent 配置归一化与探测装配层。确保 RuntimePool 指纹与注册字段同源，
并把本地自动发现与 RuntimeConfig 组装从执行混入层剥离，降低维护成本。
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.acp.runtime.pool import RuntimePool
    from myrm_agent_harness.toolkits.acp.types import AuthMode

logger = logging.getLogger(__name__)

_CLI_DEFAULT_ARGS: dict[str, list[str]] = {
    "claude": ["-p", "--output-format", "stream-json", "--verbose"],
    "codex": ["exec", "--json", "--full-auto"],
    "gemini": ["--output-format", "stream-json", "--yolo"],
}


def _default_cli_args(agent_name: str) -> list[str]:
    """Return sensible default CLI args for a known agent, empty list otherwise."""
    return list(_CLI_DEFAULT_ARGS.get(agent_name, []))


def _auth_mode(cfg: dict[str, object]) -> AuthMode:
    """Resolve the configured auth mode, defaulting to subscription (use login state)."""
    return "api_key" if cfg.get("authMode") == "api_key" else "subscription"


def _cfg_int(cfg: dict[str, object], key: str, default: int) -> int:
    """Extract an int value from a config dict with safe fallback."""
    v = cfg.get(key, default)
    if isinstance(v, int) and not isinstance(v, bool):
        return v
    if isinstance(v, str):
        try:
            return int(v.strip())
        except ValueError:
            return default
    return default


def _normalized_env(cfg: dict[str, object]) -> dict[str, str] | None:
    """Return a stable env mapping used by RuntimeConfig or None."""
    raw_env = cfg.get("env")
    if not isinstance(raw_env, dict):
        return None

    normalized: dict[str, str] = {}
    for raw_key, raw_value in raw_env.items():
        key = raw_key if isinstance(raw_key, str) else str(raw_key)
        normalized[key] = raw_value if isinstance(raw_value, str) else str(raw_value)

    if not normalized:
        return None
    return {key: normalized[key] for key in sorted(normalized)}


def _normalized_cwd(cfg: dict[str, object]) -> str | None:
    """Return cwd normalized exactly as RuntimeConfig input semantics."""
    raw_cwd = cfg.get("cwd")
    if not raw_cwd:
        return None
    return str(raw_cwd)


@dataclass(frozen=True, slots=True)
class _NormalizedRuntimeCfg:
    name: str
    backend_type: str
    command: str
    args: list[str]
    env: dict[str, str] | None
    cwd: str | None
    timeout_seconds: int
    max_response_chars: int
    permission_mode: str
    auth_mode: AuthMode
    max_turns: int
    description: str


def _normalize_runtime_cfg(cfg: dict[str, object]) -> _NormalizedRuntimeCfg | None:
    """Normalize one external-agent entry so fingerprint and RuntimeConfig stay aligned."""
    name = cfg.get("name")
    command = cfg.get("command")
    if not name or not command:
        return None

    args_raw = cfg.get("args", [])
    args: list[str] = []
    if isinstance(args_raw, (list, tuple)):
        args = [a if isinstance(a, str) else str(a) for a in args_raw]

    return _NormalizedRuntimeCfg(
        name=str(name),
        backend_type=str(cfg.get("type", "cli")),
        command=str(command),
        args=args,
        env=_normalized_env(cfg),
        cwd=_normalized_cwd(cfg),
        timeout_seconds=_cfg_int(cfg, "timeout", 300),
        max_response_chars=_cfg_int(cfg, "maxResponseChars", 50_000),
        permission_mode=str(cfg.get("permissionMode", "allow_all")),
        auth_mode=_auth_mode(cfg),
        max_turns=_cfg_int(cfg, "maxTurns", 25),
        description=str(cfg.get("description", "")),
    )


def _config_fingerprint(agent_cfgs: list[dict[str, object]]) -> str:
    """Stable hash of enabled external agent configs for pool invalidation."""
    normalized: list[dict[str, object]] = []
    for cfg in agent_cfgs:
        if not cfg.get("enabled", True):
            continue
        runtime_cfg = _normalize_runtime_cfg(cfg)
        if runtime_cfg is None:
            continue
        normalized.append(
            {
                "name": runtime_cfg.name,
                "type": runtime_cfg.backend_type,
                "command": runtime_cfg.command,
                "args": runtime_cfg.args,
                "authMode": runtime_cfg.auth_mode,
                "env": runtime_cfg.env,
                "cwd": runtime_cfg.cwd,
                "timeout": runtime_cfg.timeout_seconds,
                "maxResponseChars": runtime_cfg.max_response_chars,
                "permissionMode": runtime_cfg.permission_mode,
                "maxTurns": runtime_cfg.max_turns,
                "description": runtime_cfg.description,
            }
        )
    normalized.sort(
        key=lambda item: (
            str(item.get("name", "")),
            str(item.get("type", "")),
            str(item.get("command", "")),
            json.dumps(item.get("args", []), ensure_ascii=False, separators=(",", ":")),
        )
    )
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


async def _resolve_external_agent_cfgs(
    external_agents_config: list[dict[str, object]] | None,
) -> list[dict[str, object]] | None:
    agent_cfgs = external_agents_config
    if agent_cfgs:
        return agent_cfgs

    from app.config.deploy_mode import is_local_mode

    if not is_local_mode():
        return None

    try:
        from myrm_agent_harness.toolkits.acp.backend_detector import BackendDetector

        detector = BackendDetector()
        detected = await detector.detect(include_version=False)
        if not detected:
            return None
        agent_cfgs = [
            {
                "name": d.name,
                "type": "cli",
                "command": d.path,
                "args": _default_cli_args(d.name),
                "enabled": True,
            }
            for d in detected
        ]
        logger.info("Auto-detected %d external agent(s) in local mode", len(agent_cfgs))
        return agent_cfgs
    except Exception as e:
        logger.warning("External agent auto-detection failed (degraded): %s", e)
        return None


def _register_backends_on_pool(pool: RuntimePool, agent_cfgs: list[dict[str, object]]) -> None:
    from myrm_agent_harness.toolkits.acp.types import RuntimeConfig

    for cfg in agent_cfgs:
        if not cfg.get("enabled", True):
            continue

        normalized_cfg = _normalize_runtime_cfg(cfg)
        if normalized_cfg is None:
            logger.warning("Skipping external agent with missing name or command: %s", cfg)
            continue

        backend_type = normalized_cfg.backend_type
        if backend_type not in ("cli", "acp", "sdk"):
            logger.warning(
                "Skipping external agent '%s': invalid type '%s'",
                normalized_cfg.name,
                backend_type,
            )
            continue

        runtime_cfg = RuntimeConfig(
            backend_type=backend_type,
            command=normalized_cfg.command,
            args=normalized_cfg.args,
            env=normalized_cfg.env,
            cwd=normalized_cfg.cwd,
            timeout_seconds=normalized_cfg.timeout_seconds,
            max_response_chars=normalized_cfg.max_response_chars,
            permission_mode=normalized_cfg.permission_mode,
            auth_mode=normalized_cfg.auth_mode,
            max_turns=normalized_cfg.max_turns,
            description=normalized_cfg.description,
        )
        pool.register(normalized_cfg.name, runtime_cfg)
        logger.info("Registered external agent: %s (%s)", normalized_cfg.name, backend_type)
