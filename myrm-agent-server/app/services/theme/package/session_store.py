"""In-memory inspect session store with TTL for theme package imports.

[INPUT]
app.services.theme.package.constants::INSPECT_SESSION_TTL_SECONDS (POS: 会话 TTL)
app.services.theme.package.manifest::ThemePackageManifestModel (POS: manifest 模型)

[OUTPUT]
create_session(result) -> session_id: str
consume_session(session_id) -> ThemePackageInspectSession (一次性消费)

[POS]
线程安全的内存 session store；inspect 生成 session，install 一次性消费；
后台守护清理过期 session (默认 30 分钟)。
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field

from app.services.theme.package.constants import INSPECT_SESSION_TTL_SECONDS
from app.services.theme.package.manifest import ThemePackageManifestModel


@dataclass(slots=True)
class ThemePackageInspectSession:
    session_id: str
    package_sha256: str
    manifest: ThemePackageManifestModel
    files: dict[str, bytes]
    hero_filename: str | None
    preview_filename: str | None
    warnings: list[str] = field(default_factory=list)
    can_import: bool = True
    created_at: float = field(default_factory=time.time)


_lock = threading.Lock()
_sessions: dict[str, ThemePackageInspectSession] = {}


def _purge_expired(now: float) -> None:
    expired = [
        session_id
        for session_id, session in _sessions.items()
        if now - session.created_at > INSPECT_SESSION_TTL_SECONDS
    ]
    for session_id in expired:
        _sessions.pop(session_id, None)


def create_session(
    *,
    package_sha256: str,
    manifest: ThemePackageManifestModel,
    files: dict[str, bytes],
    hero_filename: str | None,
    preview_filename: str | None,
    warnings: list[str],
    can_import: bool,
) -> ThemePackageInspectSession:
    session = ThemePackageInspectSession(
        session_id=str(uuid.uuid4()),
        package_sha256=package_sha256,
        manifest=manifest,
        files=files,
        hero_filename=hero_filename,
        preview_filename=preview_filename,
        warnings=warnings,
        can_import=can_import,
    )
    now = time.time()
    with _lock:
        _purge_expired(now)
        _sessions[session.session_id] = session
    return session


def get_session(session_id: str) -> ThemePackageInspectSession | None:
    now = time.time()
    with _lock:
        _purge_expired(now)
        session = _sessions.get(session_id)
        if session is None:
            return None
        if now - session.created_at > INSPECT_SESSION_TTL_SECONDS:
            _sessions.pop(session_id, None)
            return None
        return session


def consume_session(session_id: str) -> ThemePackageInspectSession | None:
    now = time.time()
    with _lock:
        _purge_expired(now)
        return _sessions.pop(session_id, None)
