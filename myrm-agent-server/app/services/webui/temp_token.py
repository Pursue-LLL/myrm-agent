"""
[INPUT]
- app.config.settings::settings.webui (POS: token TTL and rate limits)
- app.services.webui.pending_setup_store (POS: disk-backed pending token)

[OUTPUT]
- TempTokenService.generate_token / consume_token / validate_token
- temp_token_service singleton

[POS]
WebUI 首次 setup 短期令牌（内存 + 磁盘，支持 WEBUI_SETUP_TOKEN 注入）。
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from dataclasses import dataclass

from app.config.settings import settings
from app.services.webui.pending_setup_store import (
    clear_pending_setup_token,
    load_pending_setup_token,
    save_pending_setup_token,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _TokenEntry:
    token: str
    expires_at: float


class TempTokenService:
    """Setup token store with hourly rate limiting and disk persistence."""

    def __init__(self) -> None:
        self._entries: dict[str, _TokenEntry] = {}
        self._issued_timestamps: list[float] = []
        self._bootstrap_from_disk()
        self._bootstrap_from_env()

    def _register(self, token: str, expires_at: float, *, persist: bool) -> None:
        self._entries[token] = _TokenEntry(token=token, expires_at=expires_at)
        if persist:
            save_pending_setup_token(token, expires_at)

    def _bootstrap_from_disk(self) -> None:
        pending = load_pending_setup_token()
        if pending is None:
            return
        token, expires_at = pending
        self._entries[token] = _TokenEntry(token=token, expires_at=expires_at)

    def _bootstrap_from_env(self) -> None:
        env_token = os.getenv("WEBUI_SETUP_TOKEN", "").strip()
        if not env_token:
            return
        expiry = float(settings.webui.token_expiry)
        expires_at = time.time() + expiry
        self._register(env_token, expires_at, persist=True)
        logger.info("WebUI setup token loaded from WEBUI_SETUP_TOKEN")

    def _prune_expired(self) -> None:
        now = time.time()
        expired = [key for key, entry in self._entries.items() if entry.expires_at <= now]
        for key in expired:
            del self._entries[key]
        if expired:
            clear_pending_setup_token()
        self._issued_timestamps = [ts for ts in self._issued_timestamps if now - ts < 3600]

    def _can_issue(self) -> bool:
        self._prune_expired()
        return len(self._issued_timestamps) < settings.webui.token_max_per_hour

    def generate_token(self) -> str:
        if not self._can_issue():
            raise RuntimeError("WebUI temp token hourly limit exceeded")
        token = secrets.token_urlsafe(32)
        expires_at = time.time() + float(settings.webui.token_expiry)
        self._register(token, expires_at, persist=True)
        self._issued_timestamps.append(time.time())
        return token

    def consume_token(self, token: str) -> bool:
        self._prune_expired()
        entry = self._entries.get(token)
        if entry is None or entry.expires_at <= time.time():
            return False
        del self._entries[token]
        clear_pending_setup_token()
        return True

    def validate_token(self, token: str) -> bool:
        self._prune_expired()
        entry = self._entries.get(token)
        return entry is not None and entry.expires_at > time.time()


temp_token_service = TempTokenService()


__all__ = ["TempTokenService", "temp_token_service"]
