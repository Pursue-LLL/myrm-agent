"""Optional repo-declared command prefixes from ``.myrm/config.toml``.

[INPUT]
- logging::logging (POS: Python 标准日志库)
- tomllib::tomllib (POS: Python TOML 解析标准库)
- pathlib::Path (POS: Python 面向对象路径标准库)
- core.security.path::read_text_bounded, ReadRefusal (POS: text read that stops at a character limit and never waits on a FIFO or device)

[OUTPUT]
- MAX_WORKSPACE_CONFIG_CHARS: the most characters the trust disclosure reads from one workspace config file
- load_repo_command_prefixes: declared shell command prefixes as tuple[str, ...],
  or () when the config is absent, unreadable, too large, or declares none
- partition_command_prefixes: split declared prefixes into the ones the user approved and the ones still pending

[POS]
Repo-policy reader of the workspace_trust gate. Read-only and fail-soft: a malformed or
missing `.myrm/config.toml` yields no prefixes rather than an error, because these
prefixes only widen what a TRUSTED workspace may run and must never block startup.
The file is read through the bounded reader: it is read before the user has decided anything about the folder,
so its size and kind are the folder's choice.
The file sits inside the workspace, so whoever can write the workspace can write it:
a declared prefix takes effect only once the user has seen it (see `partition_command_prefixes`).
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path

from myrm_agent_harness.core.security.path import ReadRefusal, read_text_bounded

logger = logging.getLogger(__name__)

# Real configs are a few kilobytes; the limit is far above that and far below what a hostile folder could make the prompt read.
MAX_WORKSPACE_CONFIG_CHARS = 1_048_576
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
        read = read_text_bounded(config_path, MAX_WORKSPACE_CONFIG_CHARS)
        if read.text is None:
            reason = (
                f"larger than {MAX_WORKSPACE_CONFIG_CHARS} characters"
                if read.refusal is ReadRefusal.TOO_LARGE
                else "not a regular file"
            )
            logger.warning("Not reading %s: %s", config_path, reason)
            return ()
        data = tomllib.loads(read.text)
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
