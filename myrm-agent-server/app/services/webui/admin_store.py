"""
[INPUT]
- app.config.settings::settings.database.state_dir (POS: workspace root path)

[OUTPUT]
- WebuiAdminRecord: persisted admin username + password hash
- admin_is_configured / load_admin / save_admin

[POS]
WebUI 单租户管理员凭据持久化（~/.myrm/webui/admin.json）。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.config.settings import settings

logger = logging.getLogger(__name__)

_ADMIN_RELATIVE = Path("webui") / "admin.json"


@dataclass(frozen=True, slots=True)
class WebuiAdminRecord:
    username: str
    password_hash: str
    created_at: str


def _admin_path() -> Path:
    base = Path(settings.database.state_dir)
    return base / _ADMIN_RELATIVE


def admin_is_configured() -> bool:
    path = _admin_path()
    return path.is_file() and path.stat().st_size > 0


def load_admin() -> WebuiAdminRecord | None:
    path = _admin_path()
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read WebUI admin config: %s", exc)
        return None
    username = raw.get("username")
    password_hash = raw.get("password_hash")
    created_at = raw.get("created_at")
    if not isinstance(username, str) or not isinstance(password_hash, str):
        return None
    if not isinstance(created_at, str):
        created_at = datetime.now(UTC).isoformat()
    return WebuiAdminRecord(username=username, password_hash=password_hash, created_at=created_at)


def delete_admin() -> None:
    path = _admin_path()
    if path.is_file():
        path.unlink(missing_ok=True)


def save_admin(username: str, password_hash: str) -> WebuiAdminRecord:
    path = _admin_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = WebuiAdminRecord(
        username=username,
        password_hash=password_hash,
        created_at=datetime.now(UTC).isoformat(),
    )
    path.write_text(
        json.dumps(
            {
                "username": record.username,
                "password_hash": record.password_hash,
                "created_at": record.created_at,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)
    return record


__all__ = ["WebuiAdminRecord", "admin_is_configured", "delete_admin", "load_admin", "save_admin"]
