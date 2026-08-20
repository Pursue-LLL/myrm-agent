"""Plugin import session staging persistence.

Persists parsed preview sessions (pickle) under the skill store data directory
with a 24h TTL cleanup for abandoned uploads.

[INPUT]
- ._models::PluginImportSession (POS: business-layer import session DTO.)

[OUTPUT]
- PluginStaging: save / load / cleanup of import sessions; expired-session sweep.

[POS]
Business-layer staging area for plugin import preview→confirm hand-off.
"""

from __future__ import annotations

import asyncio
import logging
import pickle
import time
from pathlib import Path

from ._models import PluginImportSession

logger = logging.getLogger(__name__)

_SESSION_TTL_SECONDS = 86400


class PluginStaging:
    """Persistent staging for parsed plugin sessions (mirrors SkillStagingManager)."""

    def __init__(self, base_dir: Path) -> None:
        self.staging_dir = base_dir / "plugin_staging"
        self.staging_dir.mkdir(parents=True, exist_ok=True)

    def save_session(self, session_id: str, session: PluginImportSession) -> None:
        path = self._session_path(session_id)
        try:
            with open(path, "wb") as f:
                pickle.dump(session, f)
        except Exception as exc:
            logger.error("Failed to save plugin staging session %s: %s", session_id, exc)
            raise RuntimeError("Failed to persist the plugin import session.") from exc

    def load_session(self, session_id: str) -> PluginImportSession:
        path = self._session_path(session_id)
        if not path.exists():
            raise FileNotFoundError(f"Plugin import session {session_id} not found in staging area.")
        try:
            with open(path, "rb") as f:
                loaded = pickle.load(f)  # noqa: S301
            if not isinstance(loaded, PluginImportSession):
                raise RuntimeError("Plugin staging session is corrupted")
            return loaded
        except Exception as exc:
            logger.error("Failed to load plugin staging session %s: %s", session_id, exc)
            raise RuntimeError("Failed to read the plugin import session.") from exc

    def cleanup_session(self, session_id: str) -> None:
        path = self._session_path(session_id)
        if path.exists():
            try:
                path.unlink()
            except OSError as exc:
                logger.warning("Failed to cleanup plugin staging file %s: %s", path, exc)

    def _cleanup_expired_sessions_sync(self) -> None:
        """Remove plugin sessions older than the TTL (abandoned uploads)."""
        now = time.time()
        try:
            for f in self.staging_dir.glob("*.pkl"):
                if f.is_file() and now - f.stat().st_mtime > _SESSION_TTL_SECONDS:
                    try:
                        f.unlink()
                    except OSError:
                        pass
        except Exception as exc:
            logger.warning("Failed to cleanup expired plugin sessions: %s", exc)

    async def cleanup_expired_sessions(self) -> None:
        """Remove plugin sessions older than the TTL via background thread."""
        await asyncio.to_thread(self._cleanup_expired_sessions_sync)

    def _session_path(self, session_id: str) -> Path:
        safe_id = "".join(c for c in session_id if c.isalnum() or c in "-_")
        return self.staging_dir / f"{safe_id}.pkl"
