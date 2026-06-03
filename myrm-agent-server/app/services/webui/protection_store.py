"""
[INPUT]
- app.config.deploy_mode::is_webui_remote_mode (POS: default protection when unset)
- app.config.settings::settings.database.state_dir (POS: workspace root)

[OUTPUT]
- is_password_protection_enabled: whether LAN/remote browser login is required
- set_password_protection_enabled: persist operator preference

[POS]
WebUI 访问密码保护开关（GUI 同步，非业务 env）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config.deploy_mode import is_webui_remote_mode
from app.config.settings import settings

logger = logging.getLogger(__name__)

_PROTECTION_RELATIVE = Path("webui") / "protection.json"


def _protection_path() -> Path:
    return Path(settings.database.state_dir) / _PROTECTION_RELATIVE


def _read_raw() -> dict[str, object] | None:
    path = _protection_path()
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read WebUI protection config: %s", exc)
        return None
    return raw if isinstance(raw, dict) else None


def is_password_protection_enabled() -> bool:
    raw = _read_raw()
    if raw is not None and isinstance(raw.get("require_password"), bool):
        return bool(raw["require_password"])
    return is_webui_remote_mode()


def set_password_protection_enabled(enabled: bool) -> None:
    path = _protection_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"require_password": enabled}, indent=2),
        encoding="utf-8",
    )
    path.chmod(0o600)


__all__ = ["is_password_protection_enabled", "set_password_protection_enabled"]
