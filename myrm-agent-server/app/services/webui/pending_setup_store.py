"""
[INPUT]
- app.config.settings::settings.database.state_dir (POS: workspace root)

[OUTPUT]
- save_pending_setup_token / load_pending_setup_token / clear_pending_setup_token

[POS]
持久化未消费的 WebUI setup token，避免进程重启丢失首次配置链路。
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from app.config.settings import settings

logger = logging.getLogger(__name__)

_PENDING_RELATIVE = Path("webui") / "pending_setup.json"


def _pending_path() -> Path:
    return Path(settings.database.state_dir) / _PENDING_RELATIVE


def save_pending_setup_token(token: str, expires_at: float) -> None:
    path = _pending_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"token": token, "expires_at": expires_at}, indent=2),
        encoding="utf-8",
    )
    path.chmod(0o600)


def load_pending_setup_token() -> tuple[str, float] | None:
    path = _pending_path()
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read pending setup token: %s", exc)
        return None
    token = raw.get("token")
    expires_at = raw.get("expires_at")
    if not isinstance(token, str) or not isinstance(expires_at, (int, float)):
        return None
    if float(expires_at) <= time.time():
        clear_pending_setup_token()
        return None
    return token, float(expires_at)


def clear_pending_setup_token() -> None:
    path = _pending_path()
    if path.is_file():
        path.unlink(missing_ok=True)


__all__ = [
    "clear_pending_setup_token",
    "load_pending_setup_token",
    "save_pending_setup_token",
]
