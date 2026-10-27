"""Optional repo-declared command prefixes from ``.myrm/config.toml``.

[INPUT]
- logging::logging (POS: Python 标准日志库)
- tomllib::tomllib (POS: Python TOML 解析标准库)
- pathlib::Path (POS: Python 面向对象路径标准库)

[OUTPUT]
- load_repo_command_prefixes: declared shell command prefixes as tuple[str, ...],
  or () when the config is absent, unreadable, or declares none
- partition_command_prefixes: split declared prefixes into the ones the user approved and the ones still pending

[POS]
Repo-policy reader of the workspace_trust gate. Read-only and fail-soft: a malformed or
missing `.myrm/config.toml` yields no prefixes rather than an error, because these
prefixes only widen what a TRUSTED workspace may run and must never block startup.
The file sits inside the workspace, so whoever can write the workspace can write it:
a declared prefix takes effect only once the user has seen it (see `partition_command_prefixes`).
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_RELATIVE = Path(".myrm") / "config.toml"
_PREFIX_KEYS = (
    "command_allowlist_prefixes",
    "command_allowlist_prefix",
    "command_prefixes",
)


def load_repo_command_prefixes(workspace_root: str | Path) -> tuple[str, ...]:
    """Load declared shell command prefixes from ``.myrm/config.toml`` when present."""
    root = Path(workspace_root)
    config_path = root / _CONFIG_RELATIVE
    if not config_path.is_file():
        return ()

    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to parse %s: %s", config_path, exc)
        return ()

    security = data.get("security")
    if not isinstance(security, dict):
        return ()

    prefixes: list[str] = []
    for key in _PREFIX_KEYS:
        raw = security.get(key)
        if isinstance(raw, str) and raw.strip():
            prefixes.append(raw.strip())
        elif isinstance(raw, list):
            prefixes.extend(str(item).strip() for item in raw if str(item).strip())

    # Stable order, deduplicated.
    seen: set[str] = set()
    ordered: list[str] = []
    for prefix in prefixes:
        if prefix not in seen:
            seen.add(prefix)
            ordered.append(prefix)
    return tuple(ordered)


def partition_command_prefixes(
    declared: tuple[str, ...],
    disclosed: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split *declared* into ``(approved, pending)``: approved are exactly the prefixes the user was shown."""
    shown = frozenset(disclosed)
    approved = tuple(prefix for prefix in declared if prefix in shown)
    pending = tuple(prefix for prefix in declared if prefix not in shown)
    return approved, pending
